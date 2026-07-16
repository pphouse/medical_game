from django.conf import settings
from django.db import models


class Question(models.Model):
    """spec: Question: id, category, difficulty, exam_type, choices(JSON),
    explanation, creator_id(FK, null=official), visibility, correct_rate(batch)

    Note: `choices` is stored as a JSON list of {"key": "A", "text": "..."}.
    `correct_choice_key` is added (not explicitly in the spec table) so the
    API can grade answers without leaking the correct choice in the JSON
    payload sent to the client before answering.
    """

    class ExamType(models.TextChoices):
        CBT = "CBT", "CBT"
        KOKUSHI = "KOKUSHI", "医師国家試験"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "公開（全ユーザー）"
        UNIVERSITY_ONLY = "university_only", "学内限定"

    class Difficulty(models.IntegerChoices):
        EASY = 1, "易"
        NORMAL = 2, "標準"
        HARD = 3, "難"

    category = models.CharField(max_length=100)
    topic = models.CharField(
        max_length=100,
        blank=True,
        help_text="カテゴリ内のサブトピック（疾患名など、任意）",
    )
    difficulty = models.IntegerField(
        choices=Difficulty.choices, default=Difficulty.NORMAL
    )
    exam_type = models.CharField(max_length=10, choices=ExamType.choices)
    question_text = models.TextField(
        blank=True, help_text="設問文（症例文など）"
    )
    choices = models.JSONField(
        help_text='[{"key": "A", "text": "..."}, ...]'
    )
    correct_choice_key = models.CharField(max_length=4)
    explanation = models.TextField()
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_questions",
        help_text="nullの場合は公式問題",
    )
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    university = models.ForeignKey(
        "accounts.University",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
        help_text="visibility=university_onlyの場合の閲覧範囲",
    )
    correct_rate = models.FloatField(
        default=0.0, help_text="バッチ集計される全体正答率"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "問題"
        verbose_name_plural = "問題"

    def __str__(self):
        return f"[{self.category}] {self.id}"


class AnswerHistory(models.Model):
    """spec: AnswerHistory: id, user_id, question_id, mastery_level, correct,
    answered_at, response_time_ms"""

    class MasteryLevel(models.TextChoices):
        DOUBLE_CIRCLE = "double_circle", "◎"
        CIRCLE = "circle", "○"
        TRIANGLE = "triangle", "△"
        CROSS = "cross", "✕"
        UNSTUDIED = "unstudied", "未演習"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="answer_histories"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="answer_histories"
    )
    mastery_level = models.CharField(
        max_length=20,
        choices=MasteryLevel.choices,
        default=MasteryLevel.UNSTUDIED,
    )
    correct = models.BooleanField()
    answered_at = models.DateTimeField(auto_now_add=True)
    response_time_ms = models.IntegerField()

    class Meta:
        verbose_name = "解答履歴"
        verbose_name_plural = "解答履歴"
        indexes = [
            models.Index(fields=["user", "question"]),
        ]

    def __str__(self):
        return f"{self.user_id} - Q{self.question_id} - {'○' if self.correct else '✕'}"


class ReviewSchedule(models.Model):
    """spec: ReviewSchedule: user_id, question_id, next_review_at,
    interval_days, ease_factor（SM-2アルゴリズムベース）"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_schedules"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="review_schedules"
    )
    next_review_at = models.DateTimeField()
    interval_days = models.FloatField(default=1)
    ease_factor = models.FloatField(default=2.5)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "復習スケジュール"
        verbose_name_plural = "復習スケジュール"
        unique_together = ("user", "question")

    def __str__(self):
        return f"{self.user_id} - Q{self.question_id} - next:{self.next_review_at:%Y-%m-%d}"
