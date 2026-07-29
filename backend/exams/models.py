from django.db import models

from quiz.models import Question


class MockExam(models.Model):
    """spec: MockExam: id, title, start_at, end_at (+フェーズ5拡張)

    open/closed は時刻から導出できるため effective_status を真とし、
    status 列は graded の確定と管理用に使う。
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "予定"
        OPEN = "open", "受験可"
        CLOSED = "closed", "終了"
        GRADED = "graded", "採点済"

    title = models.CharField(max_length=255)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )
    question_count = models.PositiveSmallIntegerField(default=100)
    duration_minutes = models.PositiveSmallIntegerField(default=120)
    target_grade_min = models.PositiveSmallIntegerField(null=True, blank=True)
    target_grade_max = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "模試"
        verbose_name_plural = "模試"

    def __str__(self):
        return self.title

    def effective_status(self, now=None):
        from django.utils import timezone

        if self.status == self.Status.GRADED:
            return self.Status.GRADED
        now = now or timezone.now()
        if now < self.start_at:
            return self.Status.SCHEDULED
        if now <= self.end_at:
            return self.Status.OPEN
        return self.Status.CLOSED

    def is_open_for(self, grade, now=None):
        if self.effective_status(now) != self.Status.OPEN:
            return False
        if grade is not None:
            if self.target_grade_min and grade < self.target_grade_min:
                return False
            if self.target_grade_max and grade > self.target_grade_max:
                return False
        return True


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
    """spec: MockResult: id, user_id, mock_exam_id, score, rank (+フェーズ5拡張)"""

    user = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="mock_results"
    )
    mock_exam = models.ForeignKey(
        MockExam, on_delete=models.CASCADE, related_name="results"
    )
    score = models.FloatField(default=0)
    rank = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    percentile = models.FloatField(null=True, blank=True)
    deviation_score = models.FloatField(null=True, blank=True, help_text="偏差値")
    section_scores = models.JSONField(
        default=dict, blank=True, help_text='{"D-5": 0.72, "D-7": 0.55, ...}'
    )
    university_rank = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "模試結果"
        verbose_name_plural = "模試結果"
        unique_together = ("user", "mock_exam")

    def __str__(self):
        return f"{self.mock_exam_id} - {self.user_id} ({self.score}点)"

    def deadline(self):
        """解答受付の締切: started_at + 制限時間 と 模試終了時刻の早い方 (spec 4-フェーズ5)."""
        import datetime

        limit = self.started_at + datetime.timedelta(
            minutes=self.mock_exam.duration_minutes
        )
        return min(limit, self.mock_exam.end_at)


class MockAnswer(models.Model):
    """模試の解答 (spec 2.2)。AnswerHistory とは分離する — 模試中は正誤を
    返さないため。採点後 grade_mock_exam が context=mock で AnswerHistory に
    複写する（習熟度は付与しない＝未演習のまま）。"""

    mock_result = models.ForeignKey(
        MockResult, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choice_key = models.CharField(max_length=4, blank=True, default="")
    answered_at = models.DateTimeField(auto_now=True)
    response_time_ms = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "模試解答"
        verbose_name_plural = "模試解答"
        unique_together = ("mock_result", "question")

    def __str__(self):
        return f"{self.mock_result_id} - Q{self.question_id}"


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
