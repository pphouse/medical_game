"""scripts/import_kokushi.py のうち、PDFに依存しない部分の検査。

国試のPDFはリポジトリに置かない（厚生労働省から取得する）ので、取り込みの
全体はCIでは流せない。字形の表、欧文の語間、選択肢と連問の段落の切り分け、
版下の情報の除去を、小さな入力で確かめる。どれも第106〜119回を取り込み
直したときに、実際の化け方から足した処理。
"""

import importlib.util
import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def ik():
    spec = importlib.util.spec_from_file_location(
        "import_kokushi", ROOT / "scripts" / "import_kokushi.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _char(text, x0, width=5.0, top=100.0, size=10.0):
    return {"text": text, "x0": x0, "x1": x0 + width, "top": top, "size": size}


def _word(text, x0, top=100.0, size=10.0, width=5.0):
    return [_char(ch, x0 + i * width, width, top, size) for i, ch in enumerate(text)]


def _joined(ik, chars):
    return "".join(c["text"] for c in ik._with_column_separators(chars))


class TestGlyphOutlines:
    def test_table_is_well_formed(self, ik):
        assert ik.GLYPH_OUTLINES
        for key, text in ik.GLYPH_OUTLINES.items():
            assert re.fullmatch(r"[0-9a-f]{16}", key), key
            assert text and not ik.has_broken_glyph(text), (key, text)
            assert all(unicodedata.category(ch)[0] != "C" for ch in text), (key, text)

    def test_outline_key_is_pinned(self, ik):
        # 表の指紋はこの作り方で作ってある。作り方を変えると表がすべて
        # 当たらなくなり、数字や括弧が黙って化けた本文に戻る。
        commands = [
            ("moveTo", ((0, 0),)),
            ("lineTo", ((500, 0),)),
            ("curveTo", ((600, 100), (600, 200), (500.04, 300))),
            ("closePath", ()),
        ]
        assert ik._outline_key(commands) == "52fc1d2e3f0bcf90"

    def test_outline_key_ignores_number_type_and_implied_points(self, ik):
        ints = [("moveTo", ((0, 0),)), ("qCurveTo", ((10, 10), (20, 0), None)), ("closePath", ())]
        floats = [("moveTo", ((0.0, 0.0),)), ("qCurveTo", ((10.0, 10.0), (20.0, 0.0))), ("closePath", ())]
        assert ik._outline_key(ints) == ik._outline_key(floats)
        assert ik._outline_key([]) == ""

    def test_shape_decides_over_what_the_pdf_claims(self, ik):
        paren = next(k for k, v in ik.GLYPH_OUTLINES.items() if v == "（")
        # 第106回の「蛋白8−:」: 開き括弧の字形が '8' を名乗っていた
        assert ik.shape_decision("8", paren) == "（"
        assert ik.shape_decision("�", paren) == "（"

    def test_unknown_glyph_without_a_name_is_unresolved(self, ik):
        unknown = "0123456789abcdef"
        assert unknown not in ik.GLYPH_OUTLINES
        for claimed in (" ", "　", "�", "\x02"):
            assert ik.shape_decision(claimed, unknown) == ik.UNRESOLVED, repr(claimed)
        # 名乗る文字がふつうの字なら、表に無い字形でもそのまま
        assert ik.shape_decision("あ", unknown) is None

    def test_real_blanks_and_unreadable_fonts(self, ik):
        assert ik.shape_decision(" ", "") is None  # 輪郭の無い空白
        assert ik.shape_decision(" ", None) is None  # フォントが読めない
        assert ik.shape_decision("�", None) == ik.UNRESOLVED


class TestWordGaps:
    """欧文の語間（0.3em ほどの隙間）に空白を補う。"""

    def test_english_words_are_separated(self, ik):
        chars = _word("room", 0) + _word("air", 23)  # 3pt 空く
        assert _joined(ik, chars) == "room air"

    def test_subscript_in_the_gap_is_not_a_word_break(self, ik):
        # "mmH2O" の 2 は下付きで行の組み分けが別になり、H と O が隣に見える
        chars = [_char("H", 0, top=98.9), _char("2", 5, width=3, top=102.0, size=6.4),
                 _char("O", 8, top=98.9)]
        assert " " not in _joined(ik, chars)

    def test_letter_spaced_line_is_not_split(self, ik):
        # 第117回の "Na 136mEq/L" は字ごとに 1.6pt 空けて組んである
        chars = [_char(ch, i * 6.6, size=9.9) for i, ch in enumerate("mEq")]
        assert _joined(ik, chars) == "mEq"

    def test_unit_with_a_slash_stays_together(self, ik):
        chars = _word("g/g", 0) + _word("Cr", 18)
        assert _joined(ik, chars) == "g/gCr"

    def test_japanese_and_numbers_are_untouched(self, ik):
        chars = _word("40", 0) + [_char("歳", 13, width=10)]
        assert _joined(ik, chars) == "40歳"


BLOCK = [
    "次の文を読み、1、2の問いに答えよ。",
    "症例文である。",
    "1 最初の設問はどれか。",
    "ａ 甲", "ｂ 乙", "ｃ 丙", "ｄ 丁", "ｅ 戊",
    "その後の経過 ： 翌日に発熱し、呼吸困難が出現したため再度来院した。",
    "2 次の設問はどれか。",
    "ａ 子", "ｂ 丑", "ｃ 寅", "ｄ 卯", "ｅ 辰",
]


class TestChoicesAndInterludes:
    def test_options_after_e_are_counted_separately(self, ik):
        # 6択の設問を ｅ の続きとして読むと「早産 — 死産届不要ｆ 早産 — 死産届必要」になる
        lines = ["1 正しいのはどれか。", "ａ 甲", "ｂ 乙", "ｃ 丙", "ｄ 丁", "ｅ 戊", "ｆ 己"]
        [(num, stem, texts, interlude)] = ik.parse_block(lines)
        assert (num, stem, interlude) == (1, "正しいのはどれか。", "")
        assert texts == ["甲", "乙", "丙", "丁", "戊", "己"]

    def test_interlude_moves_to_the_next_question_of_the_series(self, ik):
        parsed = ik.parse_block(BLOCK)
        first, second = parsed
        assert first[2][-1] == "戊"
        assert first[3].startswith("その後の経過")

        groups = ik.series_groups(BLOCK)
        (_, _, texts1, case1), (_, _, _, case2) = ik.attach_interludes(parsed, groups)
        assert texts1[-1] == "戊"
        assert case1 == ["症例文である。"]
        assert case2 == ["症例文である。", first[3]]

    def test_interlude_stays_with_the_choice_outside_a_series(self, ik):
        # 連問でなければこれまでどおり ｅ の続きとして読む（後段の検査が判断する）
        (_, _, texts, case), _ = ik.attach_interludes(ik.parse_block(BLOCK), {})
        assert texts[-1].startswith("戊その後の経過")
        assert case == []

    @pytest.mark.parametrize("spec", ["50～52", "50〜52", "50、51、52"])
    def test_three_question_series_share_the_case(self, ik, spec):
        # 第108回B50〜61は「50～52」（全角チルダ）。NFKC で "~" になり、
        # 範囲と読めずに症例文が付かなかった（B57 は設問文だけになった）
        lines = [f"次の文を読み、{spec}の問いに答えよ。", "症例文である。", "50 最初の設問はどれか。"]
        assert ik.series_groups(lines) == dict.fromkeys((50, 51, 52), "症例文である。")

    def test_image_note_is_not_an_interlude(self, ik):
        # 「別冊」の案内はその設問の画像。次の設問へ回すと、画像の要る設問が残ってしまう
        lines = BLOCK[:8] + ["別冊", "No. 3"] + BLOCK[9:]
        first, _ = ik.parse_block(lines)
        assert first[3] == ""


class TestPageNoise:
    def test_slug_lines_are_dropped(self, ik):
        lines = [
            "ｅ センチネルリンパ節生検はリンパ節郭清の適応決定に有用である。",
            "1",
            "TP01doc-Aor-11",
            "山田山企画-医師-本冊Ａ2.indd 11 — 2014/12/23 9:42",
            "4 疾患と治療薬の組合せで適切なのはどれか。",
        ]
        assert ik._clean(lines) == [lines[0], lines[4]]

    def test_bare_numbers_elsewhere_are_kept(self, ik):
        assert ik._clean(["表", "1", "2"]) == ["表", "1", "2"]


class TestStraySeparators:
    """均等割りの字間を列の境目と誤認して入った "—" を取り除く。"""

    def test_separator_before_a_word_is_dropped(self, ik):
        # 第117回E15の選択肢。後ろに空白の無い "—" もこれまでは見逃していた
        text = "触診 → 打 —診 → 聴診"
        assert ik.STRAY_SEPARATOR.search(text)
        assert ik.strip_stray_separators(text) == "触診 → 打診 → 聴診"

    def test_column_separator_is_kept(self, ik):
        text = "JCSII-30 — GCS5(E3V1M1)"
        assert not ik.STRAY_SEPARATOR.search(text)
        assert ik.strip_stray_separators(text) == text

    def test_combination_choice_gets_a_proper_separator(self, ik):
        assert ik.strip_stray_separators("喘息 —吸入", keep_as_separator=True) == "喘息 — 吸入"


class TestReference:
    def test_table_separators_are_ignored(self, ik):
        reference = ik._for_compare("該当項目数重篤な原因による頭痛の尤度比00.112.1")
        text = "該当項目数 — 重篤な原因による頭痛の尤度比0 — 0.1 1 — 2.1"
        assert ik.text_in_reference(text, reference)

    def test_swapped_characters_are_still_caught(self, ik):
        reference = ik._for_compare("白血球25,000(桿状核好中球15%)")
        assert not ik.text_in_reference("白血球25,00(0 桿状核好中球15%)", reference)
