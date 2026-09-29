"""CBT 基礎医学（出題基準 C-1〜C-5）の書き下ろし設問。

実際のCBTの過去問ではなく、コアカリの範囲で書き下ろした単問。四連問は作らない
（演習画面で4問を順に解かせられないため。docs/question-generation.md）。
取り込みは status=pending / source=llm で入り、公開には人の医学的レビューが
要る（import_questions が強制する）。

  C-1 生命現象の科学（生化学・分子生物学・細胞生物学・遺伝）
  C-2 個体の構成と機能（解剖・組織・発生・生理）
  C-3 個体の反応（微生物・免疫・薬理・放射線）
  C-4 病因と病態（病理学総論・遺伝性疾患・腫瘍）
  C-5 人の行動と心理（行動科学）

作問の制約は scripts/validate_questions.py と backend/tests/test_shipped_data.py
が持っている（設問文40〜600字・解説80〜600字、否定形で問わない、など）。
"""

from cbt_gap_questions import Q

CATEGORY = "基礎医学"


def basic(code, disease, stem, correct, distractors, explanation, difficulty="standard"):
    """1問ぶん。正答を先に書き、誤答は（選択肢, 誤りの理由）の4組で渡す。

    正答の位置はビルダが通し番号で A〜E に散らすので、ここでは気にしない。
    """
    if len(distractors) != 4:
        raise ValueError(f"{disease}: 誤答が{len(distractors)}個")
    choices = [correct] + [text for text, _ in distractors]
    rationale = {key: why for key, (_, why) in zip("BCDE", distractors, strict=True)}
    return Q(code, CATEGORY, disease, stem, choices, "A", explanation, rationale, difficulty)
