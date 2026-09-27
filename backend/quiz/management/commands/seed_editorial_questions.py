"""同梱の編集部バッチを、公開状態で問題バンクに入れる。

`import_questions` は生成したばかりのバッチを取り込むためのもので、
中身が確かめられていないので必ず status=pending にする (spec 2-1)。
一方 data/ に同梱しているバッチは、内容をレビューしたうえでリポジトリに
入れているので、審査待ちで止める意味がない。本番では migrate しか
流れないため、そこで止まると設問が永久に出てこない。

そこで「レビュー済みとして同梱したバッチ」だけをここに並べ、公開状態で
入れる。対象はこのファイルに書いたものだけで、`--file` のような任意の
ファイルを公開で入れる口は用意しない（それを許すと import_questions の
審査を素通りできてしまう）。

    python manage.py seed_editorial_questions

設問文と科目で重複を見るので、何度流しても増えない。
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from quiz.categories import normalize as normalize_category
from quiz.explanations import strip_boilerplate
from quiz.models import Question

DATA_DIR = Path(__file__).resolve().parent / "data"

# レビュー済みとして同梱しているバッチ。ここに並べたものだけを公開で入れる。
REVIEWED_BATCHES = (
    "cbt_batch_radiology_2026.json",
    "kokushi_batch_anesthesia_radiology_2026.json",
)


def build(item):
    """バッチの1件を Question の作成引数にする。"""
    text = "\n".join(
        [item["question_text"], item.get("disease", item.get("topic", ""))]
        + [c["text"] for c in item["choices"]]
    )
    category = normalize_category(
        item["category"],
        text,
        blueprint_code=item.get("blueprint_code", ""),
        exam_type=item["exam_type"],
    )
    per_choice = {
        str(key).strip().upper(): str(value).strip()
        for key, value in (item.get("distractor_rationale") or {}).items()
        if str(value).strip()
    }
    return category, dict(
        topic=item.get("disease", item.get("topic", "")),
        exam_type=item["exam_type"],
        difficulty=Question.Difficulty.NORMAL,
        question_type=item.get("question_type", Question.QuestionType.MULTIPLE_CHOICE),
        blueprint_code=item.get("blueprint_code", ""),
        class_group=item.get("class_group", ""),
        choices=[{"key": c["id"], "text": c["text"]} for c in item["choices"]],
        correct_choice_key=item["correct_choice_id"],
        explanation=strip_boilerplate(item["explanation"]),
        choice_explanations=per_choice,
        visibility=Question.Visibility.PUBLIC,
        status=Question.Status.PUBLISHED,
        source=Question.Source.LLM,
    )


def seed(batches=REVIEWED_BATCHES):
    """レビュー済みバッチを取り込み、(取り込んだ数, 既にあった数) を返す。"""
    created = existing = 0
    for name in batches:
        path = DATA_DIR / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("questions", []):
            category, defaults = build(item)
            _, was_created = Question.objects.get_or_create(
                category=category,
                question_text=item["question_text"],
                defaults=defaults,
            )
            created += int(was_created)
            existing += int(not was_created)
    return created, existing


class Command(BaseCommand):
    help = "同梱のレビュー済みバッチを公開状態で取り込む（重複は作らない）。"

    @transaction.atomic
    def handle(self, *args, **options):
        created, existing = seed()
        self.stdout.write(
            self.style.SUCCESS(
                f"取り込み {created}問 / 既にあった {existing}問"
                f"（バンク合計 {Question.objects.count()}問）"
            )
        )
