#!/usr/bin/env python3
"""CBT 基礎医学（C-1〜C-5）の書き下ろし設問を、取り込み用のバッチJSONにまとめる。

    python scripts/build_cbt_basic_batch.py

backend/quiz/management/commands/data/cbt_batch_basic_2026.json に書き出す。
設問の本体は scripts/cbt_basic_questions/ にあり、JSON は手で直さない
（tests/test_questions.py が書き出し直した結果と一致することを見ている）。

書き出したら scripts/validate_questions.py で検査する。取り込みは
import_questions が status=pending / source=llm で入れるので、公開には
人の医学的レビューが要る。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from build_cbt_gap_batch import build  # noqa: E402

# 出題基準の順。増やすときはここに足す（順番を変えると正答の位置が変わる）。
MODULES = [
    "cbt_basic_questions.c1_biomolecules",
    "cbt_basic_questions.c1_metabolism",
    "cbt_basic_questions.c1_molecular_biology",
    "cbt_basic_questions.c1_cell_genetics",
    "cbt_basic_questions.c2_histology_development",
    "cbt_basic_questions.c2_nervous",
    "cbt_basic_questions.c2_cardiovascular",
    "cbt_basic_questions.c2_respiratory",
    "cbt_basic_questions.c2_digestive",
    "cbt_basic_questions.c2_renal",
    "cbt_basic_questions.c2_endocrine_reproductive",
    "cbt_basic_questions.c2_blood_body",
    "cbt_basic_questions.c3_microbiology",
    "cbt_basic_questions.c3_immunology",
    "cbt_basic_questions.c3_pharmacology",
]

OUT = os.path.join(ROOT, "backend/quiz/management/commands/data/cbt_batch_basic_2026.json")


def main(out=OUT):
    return build(MODULES, id_prefix="basic2026", batch_id="basic2026",
                 generated_at="2026-09-27", out=out)


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
