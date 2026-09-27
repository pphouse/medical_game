"""1日の目標と、学習リマインドの送信記録。

進み具合と連続記録は AnswerHistory から毎回数え直すので、ここには持たない
（解答のたびに書き込む表を増やすと、解答の経路が遅く・壊れやすくなる）。
"""

from django.db import models


class DailyGoal(models.Model):
    """1日に解く問題数の目標。変えるたびに1行足し、過去の日は当時の目標で判定する。

    目標を上げた日に、それまでの連続記録を新しい目標で判定し直して消して
    しまわないように、履歴として持つ。最初の1行より前の日は、最初の目標で
    判定する（目標を決めた日に、それまでの学習がそのまま連続記録になる）。
    """

    profile = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="daily_goals"
    )
    questions_per_day = models.PositiveSmallIntegerField()
    effective_from = models.DateField(help_text="この日から適用する（Asia/Tokyo の日付）")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "1日の目標"
        verbose_name_plural = "1日の目標"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "effective_from"], name="habits_goal_one_per_day"
            )
        ]

    def __str__(self):
        return f"{self.profile_id} {self.questions_per_day}問 ({self.effective_from}〜)"


class ReminderLog(models.Model):
    """Web Push で送った学習リマインドの記録。同じ種類は1日1回まで。"""

    class Kind(models.TextChoices):
        DAILY = "daily", "今日の目標"
        STREAK = "streak", "連続記録"
        PAUSED = "paused", "通知のお休み"

    profile = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="reminder_logs"
    )
    sent_on = models.DateField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    template = models.CharField(max_length=20)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "学習リマインドの送信記録"
        verbose_name_plural = "学習リマインドの送信記録"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "sent_on", "kind"], name="habits_reminder_once_a_day"
            )
        ]

    def __str__(self):
        return f"{self.profile_id} {self.sent_on} {self.kind}"
