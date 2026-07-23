import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.provisioning import ensure_profile
from quiz.models import AnswerHistory, Question

# Demo-only sample students used purely to give the ランキング screens real
# data. Provisioned via accounts.provisioning.ensure_profile: real Supabase
# auth users when the Admin API is configured, local-only Profile rows
# otherwise.
#
# unique_target > 100 のユーザーだけが正答率ランキングに載る（100問ゲート,
# spec 3-2）。それ未満のユーザーは eligible=false の理由表示のデモになる。
SAMPLE_STUDENTS = [
    # (username, university, accuracy, unique_target)
    ("sample_riko", "九州大学", 0.95, 120),
    ("sample_sota", "東京大学", 0.90, 115),
    ("sample_taro", "サンプル医科大学", 0.85, 110),
    ("sample_nanami", "慶應義塾大学", 0.75, 105),
    ("sample_yui", "サンプル医科大学", 0.70, 102),
    ("sample_aoi", "東京大学", 0.65, 100),
    ("sample_ren", "京都大学", 0.80, 80),
    ("sample_daiki", "大阪大学", 0.60, 60),
    ("sample_hanako", "サンプル医科大学", 0.55, 50),
    ("sample_yuma", "東北大学", 0.50, 40),
    ("sample_mio", "京都大学", 0.45, 30),
    ("sample_haruto", "慶應義塾大学", 0.40, 25),
    ("sample_kaito", "九州大学", 0.35, 20),
    ("sample_kenji", "サンプル医科大学", 0.30, 15),
    # 大学別ランキングのデモ用: サンプル医科大学だけ5人以上の認証済み
    # メンバーを揃える (spec 3-2: 5人未満の大学は除外)
    ("sample_momo", "サンプル医科大学", 0.62, 45),
    ("sample_itsuki", "サンプル医科大学", 0.58, 35),
]


class Command(BaseCommand):
    help = (
        "Seed sample students with unique-question answer histories for the "
        "ranking demo. Run seed_demo --with-batch first (needs 100+ published "
        "questions), then `manage.py aggregate_rankings --period all`."
    )

    def handle(self, *args, **options):
        questions = list(Question.objects.published())
        if len(questions) < 120:
            self.stdout.write(
                self.style.WARNING(
                    f"published questions = {len(questions)} (<120). "
                    "100問ゲートのデモには `seed_demo --with-batch` を先に実行してください。"
                )
            )
        if not questions:
            return

        created_users = 0
        created_answers = 0
        now = timezone.now()

        for username, university_name, accuracy, unique_target in SAMPLE_STUDENTS:
            user = ensure_profile(
                email=f"{username}@example.com",
                display_name=username,
                university_name=university_name,
                student_verified=True,
            )
            created_users += 1

            if user.answer_histories.exists():
                continue  # already seeded in a previous run

            picked = random.sample(questions, min(unique_target, len(questions)))
            bulk = []
            for question in picked:
                is_correct = random.random() < accuracy
                mastery = (
                    random.choice(["double_circle", "circle"])
                    if is_correct
                    else random.choice(["triangle", "cross"])
                )
                bulk.append(
                    AnswerHistory(
                        user=user,
                        question=question,
                        mastery_level=mastery,
                        correct=is_correct,
                        response_time_ms=random.randint(3000, 45000),
                    )
                )
            # 周回分（同じ問題の2回目以降）はユニーク数に影響しないことの
            # デモとして、1割ほど重複解答を混ぜる
            for question in picked[: max(1, len(picked) // 10)]:
                bulk.append(
                    AnswerHistory(
                        user=user,
                        question=question,
                        mastery_level="circle",
                        correct=True,
                        response_time_ms=random.randint(3000, 45000),
                    )
                )

            AnswerHistory.objects.bulk_create(bulk)
            # answered_at is auto_now_add; spread answers over the past month
            for answer in AnswerHistory.objects.filter(user=user):
                AnswerHistory.objects.filter(pk=answer.pk).update(
                    answered_at=now
                    - timezone.timedelta(
                        days=random.randint(0, 29), minutes=random.randint(0, 1439)
                    )
                )
            created_answers += len(bulk)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_users} sample students, {created_answers} answers. "
                "Next: python manage.py aggregate_rankings --period all"
            )
        )
