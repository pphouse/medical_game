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
GLYPH_CORRUPTION = re.compile(r"[ぁ-んァ-ヶ一-龥][a-z]{1,3}(?![型値])[ぁ-んァ-ヶ一-龥]")

# 変換ミスで紛れるキリル文字・ハングル。ギリシャ文字は β2刺激薬などで
# 正当に使うので対象外。
FOREIGN_SCRIPT = re.compile(r"[\u0400-\u052f\uac00-\ud7af]")

# 置換文字と制御文字。取り込み時に一度これで35問を取りこぼしている。
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

    def test_question_text_is_not_empty(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = [
            f"{code}.{field}"
            for code, field, text in iter_texts(payload)
            if field.endswith("question_text") and not text.strip()
        ]
        assert not bad, "本文が空の設問がある:\n" + "\n".join(bad)
