"""問題数の薄い科目を埋めるCBT設問。

競合の科目別問題数と比べて明らかに薄い科目に足す。ここに書くのは実際の
CBTの過去問ではなく、コアカリの範囲で書き下ろした設問。取り込みは
status=pending / source=llm で入り、公開には人の医学的レビューが要る
（import_questions が強制する）。

作問の制約は scripts/validate_questions.py が持っている。
  ・設問文 40〜600字、解説 80〜600字
  ・選択肢はA〜Eの5個、本文の重複なし
  ・正答キーの分布は各15〜25%
  ・正答が最長の選択肢になるのは全体の40%未満
  ・「誤っているのはどれか」「〜でないものはどれか」「すべて選べ」は使わない
    （否定形は読み違いを誘うため。肯定形で問う）
"""

from dataclasses import dataclass, field


@dataclass
class Q:
    """1問ぶん。choices は5個、answer はそのうちのキー。"""

    blueprint_code: str
    category: str
    disease: str
    question_text: str
    choices: list[str]
    answer: str
    explanation: str
    rationale: dict[str, str] = field(default_factory=dict)
    difficulty: str = "standard"

    def to_json(self, item_id: str, target_key: str | None = None) -> dict:
        """取り込み用の1件にする。

        target_key を渡すと、正答がその位置に来るよう選択肢を回転させる。
        書いた順のまま出すと正答の位置が偏り（実際にある科目で正答が全部A
        になった）、位置から答えが読めてしまう。回転なので選択肢どうしの
        並びは崩れない。誤答理由は選択肢に付いて回る。
        """
        ids = ["A", "B", "C", "D", "E"]
        if len(self.choices) != 5:
            raise ValueError(f"{item_id}: 選択肢が{len(self.choices)}個")
        if self.answer not in ids:
            raise ValueError(f"{item_id}: 正答キー {self.answer!r}")

        # (本文, 誤答理由) の組にしてから回す。
        pairs = [(t, self.rationale.get(k, "")) for k, t in zip(ids, self.choices, strict=True)]
        at = ids.index(self.answer)
        if target_key:
            shift = (ids.index(target_key) - at) % 5
            pairs = pairs[-shift:] + pairs[:-shift] if shift else pairs
            at = ids.index(target_key)

        choices = [t for t, _ in pairs]
        rationale = {ids[i]: r for i, (_, r) in enumerate(pairs) if i != at}
        if any(not r for r in rationale.values()):
            raise ValueError(f"{item_id}: 誤答理由が欠けている")
        return {
            "id": item_id,
            "question_type": "M",
            "exam_type": "CBT",
            "blueprint_code": self.blueprint_code,
            "category": self.category,
            "disease": self.disease,
            "class_group": "",
            "difficulty": self.difficulty,
            "question_text": self.question_text,
            "choices": [{"id": i, "text": t} for i, t in zip(ids, choices, strict=True)],
            "correct_choice_id": ids[at],
            "explanation": self.explanation,
            "distractor_rationale": rationale,
        }
