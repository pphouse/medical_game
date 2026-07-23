from django.db import models
from django.utils import timezone

from quiz.models import Question


class BattleRoom(models.Model):
    """spec: BattleRoom: id, host_id, status, created_at

    ルーム制 (spec 4-1): ホストが作成 → 6桁ルームコード or URL 共有 → 参加 →
    ホストが開始。進行は BattleRound/BattleBuzz で管理する。
    """

    QUESTION_COUNT_CHOICES = [(5, "5問"), (10, "10問"), (20, "20問")]

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
    question_count = models.PositiveSmallIntegerField(
        choices=QUESTION_COUNT_CHOICES, default=10
    )
    category = models.CharField(
        max_length=100, blank=True, help_text="分野フィルタ（空なら全分野）"
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
    # 切断検知: 30秒以上応答がなければラウンドをスキップ扱いにする (spec 4-2)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "対戦参加者"
        verbose_name_plural = "対戦参加者"
        unique_together = ("room", "user")

    def __str__(self):
        return f"{self.room_id} - {self.user_id} ({self.score}点)"


class BattleRound(models.Model):
    """1問ごとのラウンド (spec 2.2)。start 時に全ラウンドを先に作成し、
    revealed_at の設定で出題、closed_at の設定で終了を表す。"""

    room = models.ForeignKey(BattleRoom, on_delete=models.CASCADE, related_name="rounds")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    round_number = models.PositiveSmallIntegerField()
    revealed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "対戦ラウンド"
        verbose_name_plural = "対戦ラウンド"
        unique_together = ("room", "round_number")
        ordering = ["round_number"]

    def __str__(self):
        return f"{self.room_id} R{self.round_number}"


class BattleBuzz(models.Model):
    """早押し record (spec 2.2)。

    順序はサーバ時刻で決定する。Supabase 経由では RPC `claim_buzz` が
    clock_timestamp() で挿入し（クライアントのタイムスタンプは一切信用
    しない, spec 4-1）、Django フォールバック経路でも DB now() を使う。
    rank=1 のみが回答権を持ち、誤答で次順位に移る。
    """

    round = models.ForeignKey(BattleRound, on_delete=models.CASCADE, related_name="buzzes")
    profile = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="battle_buzzes"
    )
    buzzed_at = models.DateTimeField(auto_now_add=True)
    selected_choice_key = models.CharField(max_length=4, blank=True, default="")
    is_correct = models.BooleanField(null=True, blank=True)
    rank = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "早押し"
        verbose_name_plural = "早押し"
        unique_together = ("round", "profile")
        indexes = [models.Index(fields=["round", "buzzed_at"])]

    def __str__(self):
        return f"{self.round_id} #{self.rank} {self.profile_id}"
