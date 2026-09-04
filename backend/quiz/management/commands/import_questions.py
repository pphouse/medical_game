import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.categories import normalize as normalize_category
from quiz.explanations import strip_boilerplate
from quiz.models import Question, QuestionSet

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DATA_FILE = DATA_DIR / "cbt_batch_core_2026.json"

DIFFICULTY_MAP = {
    "easy": Question.Difficulty.EASY,
    "standard": Question.Difficulty.NORMAL,
    "hard": Question.Difficulty.HARD,
}


def convert_choices(choices):
    # Import JSON uses {"id","text"}; the DB canonical form is {"key","text"}
    # (spec §5-10: the conversion is confined to this command).
    return [{"key": c["id"], "text": c["text"]} for c in choices]


def build_explanation(item):
    """Fold distractor_rationale into the explanation so reviewers and the
    result panel see why each wrong choice is wrong (spec 2-2)."""
    # 取り込みバッチの決まり文句（出典URL・整形の注記）は解説として読む
    # 中身が無いので、DBに入れる前に落とす。
    explanation = strip_boilerplate(item["explanation"])
    rationale = item.get("distractor_rationale")
    if rationale:
        lines = [f"{key}: {text}" for key, text in sorted(rationale.items())]
        explanation = explanation + "\n\n【誤答選択肢の解説】\n" + "\n".join(lines)
    return explanation


class Command(BaseCommand):
    help = (
        "Import questions from a JSON batch file. LLM-generated batches are "
        "ALWAYS imported as status=pending / source=llm — they must pass human "
        "review (admin or /api/quiz/review/) before publication."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=None,
            help="Path to the JSON file (see schemas/question_batch.schema.json).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help=(
                "同梱のバッチ（data/*.json）をすべて取り込む。国試は114〜119回の"
                "1000問超が同梱されているが、既定のファイルはCBTの1本だけなので、"
                "問題数が足りないときはこちらを使う。"
            ),
        )

    def handle(self, *args, **options):
        if options["all"] and options["file"]:
            raise CommandError("--all と --file は同時に指定できません")
        if options["all"]:
            paths = sorted(DATA_DIR.glob("*.json"))
            if not paths:
                raise CommandError(f"No batch files found in {DATA_DIR}")
        else:
            paths = [Path(options["file"] or DEFAULT_DATA_FILE)]

        for path in paths:
            self._import_file(path)

    @transaction.atomic
    def _import_file(self, data_path):
        if not data_path.exists():
            raise CommandError(f"File not found: {data_path}")
        payload = json.loads(data_path.read_text(encoding="utf-8"))

        created_questions = 0
        created_sets = 0

        for q in payload.get("questions", []):
            # バッチ JSON の分野名は作られた時期によってまちまちなので、
            # 取り込み時に正規の科目立てへ寄せる（quiz/categories.py）。
            # 科目立ては CBT と国試で違うので exam_type も渡す。
            category = normalize_category(
                q["category"],
                "\n".join(
                    [q["question_text"], q.get("disease", q.get("topic", ""))]
                    + [str(c.get("text", "")) for c in q["choices"] if isinstance(c, dict)]
                ),
                blueprint_code=q.get("blueprint_code", ""),
                exam_type=q["exam_type"],
            )
            _, was_created = Question.objects.get_or_create(
                category=category,
                question_text=q["question_text"],
                defaults=dict(
                    topic=q.get("disease", q.get("topic", "")),
                    exam_type=q["exam_type"],
                    difficulty=DIFFICULTY_MAP.get(
                        q.get("difficulty", "standard"), Question.Difficulty.NORMAL
                    ),
                    question_type=q.get("question_type", Question.QuestionType.MULTIPLE_CHOICE),
                    blueprint_code=q.get("blueprint_code", ""),
                    class_group=q.get("class_group", ""),
                    choices=convert_choices(q["choices"]),
                    correct_choice_key=q["correct_choice_id"],
                    explanation=build_explanation(q),
                    visibility=Question.Visibility.PUBLIC,
                    # 強制 (spec 2-1): imported batches enter the review queue.
                    status=Question.Status.PENDING,
                    source=Question.Source.LLM,
                ),
            )
            created_questions += int(was_created)

        for s in payload.get("question_sets", []):
            if QuestionSet.objects.filter(case_stem=s["case_stem"]).exists():
                continue
            set_category = normalize_category(
                s["category"],
                "\n".join([s["case_stem"], s.get("disease", "")]),
                blueprint_code=s.get("blueprint_code", ""),
                exam_type=s.get("exam_type", "CBT"),
            )
            question_set = QuestionSet.objects.create(
                title=s.get("title") or f"{s.get('disease', s['id'])}の四連問",
                blueprint_code=s.get("blueprint_code", ""),
                case_stem=s["case_stem"],
                status=Question.Status.PENDING,
                source=Question.Source.LLM,
            )
            created_sets += 1
            for step in s["steps"]:
                Question.objects.create(
                    category=set_category,
                    topic=s.get("disease", ""),
                    exam_type=s.get("exam_type", Question.ExamType.CBT),
                    difficulty=DIFFICULTY_MAP.get(
                        s.get("difficulty", "standard"), Question.Difficulty.NORMAL
                    ),
                    question_type=Question.QuestionType.SEQUENTIAL,
                    blueprint_code=s.get("blueprint_code", ""),
                    class_group=s.get("class_group", ""),
                    question_set=question_set,
                    set_order=step["set_order"],
                    question_text=step["question_text"],
                    choices=convert_choices(step["choices"]),
                    correct_choice_key=step["correct_choice_id"],
                    explanation=build_explanation(step),
                    visibility=Question.Visibility.PUBLIC,
                    status=Question.Status.PENDING,
                    source=Question.Source.LLM,
                )
                created_questions += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {created_questions} new questions / {created_sets} question sets "
                f"from {data_path.name} as status=pending (total in DB: {Question.objects.count()})."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Review required: approve via Django admin or "
                "POST /api/quiz/review/questions/<id>/approve/ before they appear in practice."
            )
        )
