"""同梱している設問データ（backend/quiz/management/commands/data/*.json）の
壊れ方を検出する。

国試は厚生労働省の PDF から取り込んでいる。本文フォントが ToUnicode を持たず
CFF のグリフ名から文字を解決しているため、解決に失敗した字がラテン文字1〜3字
として残ることがある（「両側大腿部」が「両側大fl部」、「全身倦怠感」が
「全身h怠感」になっていた）。日本語に挟まれた孤立ラテン小文字はまず字化けなので、
目視ではなく機械で落とす。
"""

import json
import re
from pathlib import Path

import pytest

from quiz.data_checks import (
    BODY_KANJI_AFTER_DIGIT,
    BRACKET_LOOKALIKE,
    DROPPED_NUMBER,
    DROPPED_WORD_HEAD,
    FIGURE_REF,
    FIGURE_REF_MIN_BODY,
    FOREIGN_SCRIPT,
    GLYPH_CORRUPTION,
    KANJI_DIGIT_KANJI,
    POSITION_KANJI_THEN_LATIN,
    STRAY_SEPARATOR,
    UNUSABLE,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "quiz/management/commands/data"


def data_files():
    return sorted(p for p in DATA_DIR.glob("*.json") if ".report." not in p.name)


def iter_texts(payload):
    """設問データの中で学習者に見えるテキストをすべて挙げる。"""
    for q in payload.get("questions", []):
        code = q.get("blueprint_code") or q.get("id") or "?"
        yield code, "question_text", q["question_text"]
        for c in q["choices"]:
            yield code, f"choices[{c['id']}]", c["text"]
        yield code, "explanation", q.get("explanation", "")
    for s in payload.get("question_sets", []):
        yield s.get("id", "?"), "case_stem", s["case_stem"]
        for step in s.get("steps", []):
            yield s.get("id", "?"), "step.question_text", step["question_text"]
            for c in step["choices"]:
                yield s.get("id", "?"), f"step.choices[{c['id']}]", c["text"]


@pytest.mark.parametrize("path", data_files(), ids=lambda p: p.name)
class TestShippedData:
    def test_question_numbers_increase(self, path):
        """設問番号はブロック内で単調に増える。

        番号が戻っていたら、症例文の折り返し（「2 日前から…」）を番号行と
        取り違えて設問を切り出している。設問文が欠けるだけでなく、正答表の
        照合先までずれるので、正答そのものが誤る（第119回C44で実際に起きた）。
        """
        payload = json.loads(path.read_text(encoding="utf-8"))
        last: dict[str, int] = {}
        bad = []
        for q in payload["questions"]:
            code = q.get("blueprint_code")
            if not code or code.count("-") != 2:
                continue
            _, block, num = code.split("-")
            num = int(num)
            if block in last and num <= last[block]:
                bad.append(f"{code}: 直前は {block}-{last[block]}")
            last[block] = num
        assert not bad, "設問番号が戻っている:\n" + "\n".join(bad)

    # 語の途中に紛れ込むダッシュ。「自己免疫— 性膵炎」のように、PDFの行を
    # つなぐときに区切り記号が本文へ落ちることがある。pdfplumber の版が
    # 変わると出方も変わるので、取り込みをやり直したときに気づけるようにする。
    # 同梱データ全2,249問で0件、いまの環境で作り直すと3件出た。
    DASH_IN_WORD = re.compile(r"[ぁ-んァ-ヶ一-龥][—–―][ぁ-んァ-ヶ一-龥]")

    def test_no_dash_inside_words(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: …{text[max(0, m.start() - 8):m.start() + 12]}…"
            for code, field, text in iter_texts(payload)
            for m in [self.DASH_IN_WORD.search(text)]
            if m
        ]
        assert not bad, "語中にダッシュが紛れている:\n" + "\n".join(bad)

    def test_no_glyph_corruption(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: …{text[max(0, m.start() - 10):m.start() + 14]}…"
            for code, field, text in iter_texts(payload)
            for m in [GLYPH_CORRUPTION.search(text)]
            if m
        ]
        assert not bad, "グリフ解決に失敗した字が残っている:\n" + "\n".join(bad)

    def test_no_foreign_script(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: {m.group()!r}"
            for code, field, text in iter_texts(payload)
            for m in [FOREIGN_SCRIPT.search(text)]
            if m
        ]
        assert not bad, "キリル文字/ハングルが紛れている:\n" + "\n".join(bad)

    def test_no_unusable_characters(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}"
            for code, field, text in iter_texts(payload)
            if UNUSABLE.search(text)
        ]
        assert not bad, "置換文字/制御文字が残っている:\n" + "\n".join(bad)

    def test_brackets_are_balanced(self, path):
        """括弧の数が合わないのは、閉じ括弧が別の字に化けた痕跡。

        国試PDFでは ')' が空白や '1' に、'(' が ':' に、'〈' が '~' に化けて
        いた。1文字化けただけでは読めてしまい目視では見つからないが、
        対応が崩れるので数を数えれば必ず出る。
        """
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: {opener}{text.count(opener)} {closer}{text.count(closer)}"
            for code, field, text in iter_texts(payload)
            for opener, closer in (("(", ")"), ("〈", "〉"), ("「", "」"))
            if text.count(opener) != text.count(closer)
        ]
        assert not bad, "括弧の対応が崩れている:\n" + "\n".join(bad)

    def test_no_question_needs_a_missing_figure(self, path):
        """「家系図を示す」と書いてあるのに図が無い設問を落とす。

        国試には図表を参照する設問があり、別冊(画像)を参照するものは取り込み時に
        除いている。ところが「家系図を示す。この疾患の遺伝形式はどれか。」のように
        本文中の図を指すものが素通りし、41字の解きようがない設問が公開まで
        通っていた。会話文や表を本文に取り込めている設問は必ず長くなるので、
        参照の文言と本文の長さで見分ける。
        """
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}: {len(text)}字 {text[:40]}"
            for code, field, text in iter_texts(payload)
            if field.endswith("question_text")
            and FIGURE_REF.search(text)
            and len(text) < FIGURE_REF_MIN_BODY
        ]
        assert not bad, "参照先の図表が本文に無い設問:\n" + "\n".join(bad)

    def test_no_dropped_numbers(self, path):
        """数詞が抜けて単位だけが残っていないか。

        「新生児死亡とは生後4週未満の死亡である」が「生後週未満」になっていた。
        グリフ解決に失敗した数字がそのまま消えたもので、文としては読めるため
        目視では気づけない。数詞が来るはずの位置を機械で見る。
        """
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: …{text[max(0, m.start() - 12):m.start() + 20]}…"
            for code, field, text in iter_texts(payload)
            for m in [DROPPED_NUMBER.search(text)]
            if m
        ]
        assert not bad, "数詞が抜けている:\n" + "\n".join(bad)

    def test_parens_do_not_span_sentences(self, path):
        """括弧の中に句点が入っていないか。

        閉じ括弧が別の字に化けたものを機械的に戻すとき、閉じる位置を取り違える
        ことがある（実際に「9点(5分)であった」を数文先で閉じてしまった）。
        日本語の括弧書きが句点をまたぐことはまずないので、これで検出できる。
        """
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: ({m.group(1)[:50]})"
            for code, field, text in iter_texts(payload)
            for m in re.finditer(r"\(([^()]*)\)", text)
            if "。" in m.group(1)
        ]
        assert not bad, "括弧が句点をまたいでいる:\n" + "\n".join(bad)

    def test_no_kanji_replaced_by_digit(self, path):
        """漢字が数字1文字に化けていないか（KANJI_DIGIT_KANJI 参照）。"""
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: …{text[max(0, m.start() - 10):m.start() + 12]}…"
            for code, field, text in iter_texts(payload)
            for m in [
                KANJI_DIGIT_KANJI.search(text)
                or BODY_KANJI_AFTER_DIGIT.search(text)
                or POSITION_KANJI_THEN_LATIN.search(text)
            ]
            if m
        ]
        assert not bad, "漢字が数字に化けている:\n" + "\n".join(bad)

    def test_no_stray_column_separator(self, path):
        """列区切りが語の途中に入っていないか（STRAY_SEPARATOR 参照）。"""
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: …{text[max(0, m.start() - 12):m.start() + 14]}…"
            for code, field, text in iter_texts(payload)
            if not field.startswith("explanation")
            for m in [STRAY_SEPARATOR.search(text)]
            if m
        ]
        assert not bad, "列区切りが語中に入っている:\n" + "\n".join(bad)

    def test_no_bracket_lookalike_or_dropped_word_head(self, path):
        """〈〉が別の記号に化けた形と、語頭の字が落ちた形を拾う。"""
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}: …{text[max(0, m.start() - 12):m.start() + 14]}…"
            for code, field, text in iter_texts(payload)
            for m in [
                BRACKET_LOOKALIKE.search(text) or DROPPED_WORD_HEAD.search(text)
            ]
            if m
        ]
        assert not bad, "記号の化け／語頭の脱落:\n" + "\n".join(bad)

    def test_combination_choices_have_separators(self, path):
        """組合せ問題の選択肢に列の区切りが入っているか。

        「疾患と症状の組合せ」型の設問は左右2列で組まれており、区切りが
        入らないと「葉酸小球性貧血」のように2列が続けて読めてしまう。
        字間から列の境目を判定しているため、間隔が狭い回では区切りが
        入らないことがあった（第117回で9問）。

        2列組みは国試PDFの組版に由来するので、この検査は国試データだけに
        かける。CBTの設問は自作で、選択肢が文になっており2列ではない。
        選択肢が数値の並びである設問も2列ではないため例外とする。
        """
        if not path.name.startswith("kokushi_"):
            pytest.skip("国試データのみが2列組み")
        payload = json.loads(path.read_text(encoding="utf-8"))
        # 2列組みではない「組合せ」設問。選択肢が文または数値の並びになっている。
        NOT_TWO_COLUMN = {"116-A-64", "118-C-56", "118-F-27"}
        bad = [
            f"{q['blueprint_code']}: {[c['text'][:24] for c in q['choices']]}"
            for q in payload.get("questions", [])
            if "組合せ" in q["question_text"]
            and q.get("blueprint_code") not in NOT_TWO_COLUMN
            and not any("—" in c["text"] for c in q["choices"])
        ]
        assert not bad, "組合せ問題に列の区切りが無い:\n" + "\n".join(bad)

    def test_question_text_is_not_empty(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}"
            for code, field, text in iter_texts(payload)
            if field.endswith("question_text") and not text.strip()
        ]
        assert not bad, "本文が空の設問がある:\n" + "\n".join(bad)
