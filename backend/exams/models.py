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
    correct_rate（questions_solved >= MIN_QUESTIONS_FOR_ACCURACY_RANKING の
    ユーザーのみ算出対象。要件は100問以上 — spec §5-1 で 1000 から修正）"""

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
        help_text="questions_solved >= exams.constants.MIN_QUESTIONS_FOR_ACCURACY_RANKING (=100) のユーザーのみ算出",
    )

    class Meta:
        verbose_name = "月間ランキング"
        verbose_name_plural = "月間ランキング"
        unique_together = ("user", "month")

    def __str__(self):
        return f"{self.month:%Y-%m} - {self.user_id}"


class RankingSnapshot(models.Model):
    """ランキング集計結果（Materialized View ではなく実テーブル + upsert,
    spec 2.2）。aggregate_rankings コマンドが (scope, university, period,
    metric) 単位で洗い替える。API はこのテーブルだけを読む。"""

    class Scope(models.TextChoices):
        NATIONAL = "national", "全国（個人）"
        UNIVERSITY = "university", "学内（個人）"
        UNIVERSITY_AGGREGATE = "university_aggregate", "大学別（大学単位）"

    class Metric(models.TextChoices):
        SOLVED = "solved", "解いた問題数"
        ACCURACY = "accuracy", "正答率"

    scope = models.CharField(max_length=30, choices=Scope.choices)
    university = models.ForeignKey(
        "accounts.University",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ranking_snapshots",
        help_text="scope=university のとき、どの大学の学内ランキングか",
    )
    period = models.CharField(max_length=7, help_text='"all" または "YYYY-MM"')
    metric = models.CharField(max_length=10, choices=Metric.choices)
    profile = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ranking_snapshots",
    )
    university_target = models.ForeignKey(
        "accounts.University",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ranked_snapshots",
        help_text="scope=university_aggregate のとき、順位づけされた大学",
    )
    rank = models.PositiveIntegerField()
    value = models.FloatField(help_text="solved=ユニーク問題数 / accuracy=初回解答の正答率(%)")
    sample_size = models.PositiveIntegerField(
        default=0, help_text="個人行=ユニーク解答問題数 / 大学行=対象メンバー数"
    )
    computed_at = models.DateTimeField()

    class Meta:
        verbose_name = "ランキングスナップショット"
        verbose_name_plural = "ランキングスナップショット"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "scope",
                    "university",
                    "period",
                    "metric",
                    "profile",
                    "university_target",
                ],
                nulls_distinct=False,
                name="uniq_ranking_snapshot_entry",
            )
        ]
        indexes = [
            models.Index(fields=["scope", "period", "metric", "rank"]),
        ]

    def __str__(self):
        return f"{self.scope}/{self.period}/{self.metric} #{self.rank}"
