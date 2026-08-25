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

DATA_DIR = Path(__file__).resolve().parent.parent / "quiz/management/commands/data"

# 日本語の文字に挟まれた孤立した半角小文字。「mmHg」「β2」のような正当な
# 表記は前後が英数字や記号なので当たらない。「インフルエンザ菌b型」「p値」の
# ように、学術表記として1文字が日本語に挟まれる形は正当なので除外する。
GLYPH_CORRUPTION = re.compile(r"[ぁ-んァ-ヶ一-龥。、）」][a-z]{1,3}(?![型値])[ぁ-んァ-ヶ一-龥]")

# 変換ミスで紛れるキリル文字・ハングル。ギリシャ文字は β2刺激薬などで
# 正当に使うので対象外。
FOREIGN_SCRIPT = re.compile(r"[\u0400-\u052f\uac00-\ud7af]")

# 置換文字と制御文字。取り込み時に一度これで35問を取りこぼしている。
# 数詞が抜けて単位だけが残った形。「生後4週未満」→「生後週未満」、
# 「4年前に高血圧症」→「年前に高血圧症」。グリフ解決に失敗した数字が
# そのまま消えたもので、文としては読めるため目視では気づけない。
QUANTIFIER = "0-9０-９一二三四五六七八九十百千万数何約半昨一昨翌前々"
DROPPED_NUMBER = re.compile(
    # 「生後週未満」型: 起点の語のすぐ後に数詞が無い
    rf"(生後|妊娠|在胎|日齢|産後|術後|病日)[^{QUANTIFIER}]?(週|日|か月|年|時間)"
    rf"(未満|以内|以後|以降|目)"
    # 「年前に」型: 期間の単位と前/後の組が数詞を伴っていない。
    # 「成年後見」を拾わないよう「見」が続く場合を除く。国試の本文では
    # 数字と単位の間に空白が入ることがあるので、空白も数詞側として扱う。
    rf"|(?<![{QUANTIFIER} ])(年前|か月前|週間前|年後|か月後)(?!見)"
)

# 漢字が数字に化けた形。「大腿動脈」→「大3動脈」、「末梢血」→「末4血」。
# 数字の後ろが助数詞や単位なら数量として自然（「1妊0産」「基準5以下」
# 「日本酒2合」）なので、内容語が続く場合だけを拾う。
# 数字の前に来ると順序数・概数になる語（第2肋間、約9割）。
ORDINAL_KANJI = "第約計比対"
COUNTER_KANJI = (
    "産以歳羊剤事合限丁杯升子回目度人名例年月日週時分秒個本番型階級点枚錠束袋"
    "割対万千肋群枝趾指椎肢横状"
)
KANJI_DIGIT_KANJI = re.compile(
    rf"(?<=[一-龥])(?<![{ORDINAL_KANJI}])[0-9](?![{COUNTER_KANJI}])(?=[一-龥])"
)

# 数詞の直後には決して来ない身体・症候の漢字。「倦怠感」→「6怠感」、
# 「末梢」→「末4血」のように、語の先頭の字が数字に化けた形を拾う。
# 前がかなでも当たるので上の規則の取りこぼしを埋める。
BODY_KANJI = "怠腿梢腕靱腱窩瘻痺攣痒疸癬疹瘡嚢囊臼蓋顆棘"
BODY_KANJI_AFTER_DIGIT = re.compile(rf"[0-9](?=[{BODY_KANJI}])")

# 方向・位置を表す字のすぐ後に英数字1文字が来て漢字が続く形。「末梢血」が
# 「末P血」、「大腿動脈」が「大3動脈」になっていた。前・後は「術後2日目」の
# ように時間表現で数字が続くのが普通なので対象から外す。
POSITION_KANJI_THEN_LATIN = re.compile(
    rf"[末大下上内外側両][0-9A-Za-z](?![{COUNTER_KANJI}])(?=[一-龥ァ-ヶ])"
)

# 語中に紛れ込んだ列区切り。組合せ問題の左右2列を見分けるため、字間が
# 広い箇所に "—" を差し込んでいる（scripts/import_kokushi.py）。均等割りで
# 広がった字間まで列の間隔と誤認され、「急性好酸球性— 肺炎」のように語の
# 途中に入っていた。正当な列区切りは前後に空白があるので、空白を伴わない
# "—" だけを拾う。
STRAY_SEPARATOR = re.compile(r"(?:(?<=[^\s])|^)—")

# 図表を参照しているのに参照先が本文に無い設問（scripts/import_kokushi.py と対）。
FIGURE_REF = re.compile(r"(家系図|図|写真|画像|グラフ|シェーマ|電気泳動|カレンダー)を(以下に|別に)?示す")
FIGURE_REF_MIN_BODY = 120

UNUSABLE = re.compile(r"[\ufffd\u0000-\u0008\u000b-\u001f\u007f-\u009f]")


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

    def test_question_text_is_not_empty(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}"
            for code, field, text in iter_texts(payload)
            if field.endswith("question_text") and not text.strip()
        ]
        assert not bad, "本文が空の設問がある:\n" + "\n".join(bad)
