import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import University, User
from quiz.models import AnswerHistory, Question

# Demo-only sample students (username prefix "sample_") used purely to give
# the 学内順位/全国順位 ranking widgets real data to display. Not real users,
# never selectable via demo-login.
SAMPLE_STUDENTS = [
    ("sample_taro", "サンプル医科大学", 0.85),
    ("sample_hanako", "サンプル医科大学", 0.55),
    ("sample_kenji", "サンプル医科大学", 0.30),
    ("sample_yui", "サンプル医科大学", 0.70),
    ("sample_sota", "東京大学", 0.90),
    ("sample_aoi", "東京大学", 0.65),
    ("sample_ren", "京都大学", 0.80),
    ("sample_mio", "京都大学", 0.45),
    ("sample_daiki", "大阪大学", 0.60),
    ("sample_nanami", "慶應義塾大学", 0.75),
    ("sample_haruto", "慶應義塾大学", 0.40),
    ("sample_yuma", "東北大学", 0.50),
    ("sample_riko", "九州大学", 0.95),
    ("sample_kaito", "九州大学", 0.35),
]


class Command(BaseCommand):
    help = "Seed sample student users with randomized answer history, for ranking demo purposes."

    def handle(self, *args, **options):
        questions = list(Question.objects.all())
        if not questions:
            self.stdout.write(self.style.WARNING("No questions found; run seed_demo first."))
            return

        created_users = 0
        created_answers = 0
        now = timezone.now()

        for username, university_name, target_accuracy in SAMPLE_STUDENTS:
            university, _ = University.objects.get_or_create(name=university_name)
            user, was_created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "university": university,
                    "student_verified": True,
                },
            )
            created_users += int(was_created)

            if user.answer_histories.exists():
                continue  # already seeded in a previous run

            num_answers = random.randint(20, 60)
            for _ in range(num_answers):
                question = random.choice(questions)
                is_correct = random.random() < target_accuracy
                mastery = (
                    random.choice(["double_circle", "circle"])
                    if is_correct
                    else random.choice(["triangle", "cross"])
                )
                answer = AnswerHistory.objects.create(
                    user=user,
                    question=question,
                    mastery_level=mastery,
                    correct=is_correct,
                    response_time_ms=random.randint(3000, 45000),
                )
                # answered_at is auto_now_add, so backdate it with a direct
                # update() (bypasses save()) to spread answers over the
                # past month instead of all clustering at "now".
                backdated_at = now - timezone.timedelta(
                    days=random.randint(0, 29), minutes=random.randint(0, 1439)
                )
                AnswerHistory.objects.filter(pk=answer.pk).update(answered_at=backdated_at)
                created_answers += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_users} new sample students, {created_answers} answer records."
            )
        )
