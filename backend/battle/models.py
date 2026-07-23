from django.db import models

from quiz.models import Question


class BattleRoom(models.Model):
    """spec: BattleRoom: id, host_id, status, created_at

    Kept decoupled from the solo-mode REST API: the WebSocket layer
    (Django Channels + Redis) will be added in phase 3 on top of these
    tables without touching quiz/exams models.
    """

    class Status(models.TextChoices):
        WAITING = "waiting", "参加者募集中"
        IN_PROGRESS = "in_progress", "対戦中"
        FINISHED = "finished", "終了"

    host = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="hosted_battle_rooms"
    )
    room_code = models.CharField(max_length=8, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.WAITING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "対戦ルーム"
        verbose_name_plural = "対戦ルーム"

    def __str__(self):
        return f"{self.room_code} ({self.status})"


class BattleParticipant(models.Model):
    """spec: BattleParticipant: room_id, user_id, score"""

    room = models.ForeignKey(
        BattleRoom, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="battle_participations"
    )
    score = models.IntegerField(default=0)

    class Meta:
        verbose_name = "対戦参加者"
        verbose_name_plural = "対戦参加者"
        unique_together = ("room", "user")

    def __str__(self):
        return f"{self.room_id} - {self.user_id} ({self.score}点)"


class BattleAnswer(models.Model):
    """spec: BattleAnswer: room_id, user_id, question_id, answered_at,
    is_correct（早押し判定はanswered_atの順序で決定）"""

    room = models.ForeignKey(
        BattleRoom, on_delete=models.CASCADE, related_name="answers"
    )
    user = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="battle_answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answered_at = models.DateTimeField(auto_now_add=True)
    is_correct = models.BooleanField()

    class Meta:
        verbose_name = "対戦回答"
        verbose_name_plural = "対戦回答"
        ordering = ["answered_at"]

    def __str__(self):
        return f"{self.room_id} - {self.user_id} - {'○' if self.is_correct else '✕'}"
