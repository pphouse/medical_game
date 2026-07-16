import json
from pathlib import Path

from django.core.management.base import BaseCommand

from quiz.models import Question

DEFAULT_DATA_FILE = (
    Path(__file__).resolve().parent / "data" / "cbt_batch_digestive_cardio.json"
)

DIFFICULTY_MAP = {
    "easy": Question.Difficulty.EASY,
    "standard": Question.Difficulty.NORMAL,
    "hard": Question.Difficulty.HARD,
}


class Command(BaseCommand):
    help = "Import questions from a JSON file (choices keyed by 'id') into Question."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=str(DEFAULT_DATA_FILE),
            help="Path to the JSON file containing a top-level 'questions' list.",
        )

    def handle(self, *args, **options):
        data_path = Path(options["file"])
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        questions = payload["questions"]

        created_count = 0
        for q in questions:
            choices = [{"key": c["id"], "text": c["text"]} for c in q["choices"]]
            _, was_created = Question.objects.get_or_create(
                category=q["category"],
                question_text=q["question_text"],
                defaults=dict(
                    topic=q.get("disease", ""),
                    exam_type=q["exam_type"],
                    difficulty=DIFFICULTY_MAP.get(
                        q.get("difficulty", "standard"), Question.Difficulty.NORMAL
                    ),
                    choices=choices,
                    correct_choice_key=q["correct_choice_id"],
                    explanation=q["explanation"],
                    visibility=Question.Visibility.PUBLIC,
                ),
            )
            created_count += int(was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {created_count} new questions from {data_path.name} "
                f"(total in DB: {Question.objects.count()})."
            )
        )
