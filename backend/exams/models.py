from django.db import models

from quiz.models import Question


class MockExam(models.Model):
    """spec: MockExam: id, title, start_at, end_at"""

    title = models.CharField(max_length=255)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    class Meta:
        verbose_name = "模試"
        verbose_name_plural = "模試"

    def __str__(self):
        return self.title


class MockQuestion(models.Model):
    """spec: MockQuestion: mock_exam_id, question_id, order"""

    mock_exam = models.ForeignKey(
        MockExam, on_delete=models.CASCADE, related_name="mock_questions"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()

    class Meta:
        verbose_name = "模試設問"
        verbose_name_plural = "模試設問"
        unique_together = ("mock_exam", "order")
        ordering = ["order"]

    def __str__(self):
        return f"{self.mock_exam_id} - 第{self.order}問"


class MockResult(models.Model):
    """spec: MockResult: id, user_id, mock_exam_id, score, rank"""

    user = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="mock_results"
    )
    mock_exam = models.ForeignKey(
        MockExam, on_delete=models.CASCADE, related_name="results"
    )
    score = models.FloatField()
    rank = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "模試結果"
        verbose_name_plural = "模試結果"
        unique_together = ("user", "mock_exam")

    def __str__(self):
        return f"{self.mock_exam_id} - {self.user_id} ({self.score}点)"


class MonthlyRanking(models.Model):
    """spec: MonthlyRanking: user_id, university_id, month, questions_solved,
    correct_rate（questions_solved >= 1000のユーザーのみ算出対象）"""

    user = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="monthly_rankings"
    )
    university = models.ForeignKey(
        "accounts.University", on_delete=models.CASCADE, related_name="monthly_rankings"
    )
    month = models.DateField(help_text="月初日で保持 (例: 2026-07-01)")
    questions_solved = models.PositiveIntegerField(default=0)
    correct_rate = models.FloatField(
        null=True,
        blank=True,
        help_text="questions_solved >= 1000のユーザーのみ算出",
    )

    class Meta:
        verbose_name = "月間ランキング"
        verbose_name_plural = "月間ランキング"
        unique_together = ("user", "month")

    def __str__(self):
        return f"{self.month:%Y-%m} - {self.user_id}"
