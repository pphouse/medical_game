from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "Nightly batch (spec §5-5): recompute Question.correct_rate and "
        "answer_count from AnswerHistory in a single SQL pass."
    )

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE quiz_question q
                SET answer_count = s.n,
                    correct_rate = s.rate
                FROM (
                    SELECT question_id,
                           COUNT(*) AS n,
                           ROUND(AVG(CASE WHEN correct THEN 1.0 ELSE 0.0 END) * 100, 1) AS rate
                    FROM quiz_answerhistory
                    GROUP BY question_id
                ) s
                WHERE q.id = s.question_id
                """
            )
            updated = cursor.rowcount
        self.stdout.write(self.style.SUCCESS(f"Recalculated correct_rate for {updated} questions."))
