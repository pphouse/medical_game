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
    # ルーム終了時に確定する対戦ランクポイントの増減（一度だけ適用する）
    points_delta = models.IntegerField(null=True, blank=True)
    # 離脱（自分から退出 or 無応答による自動退場）した時刻。null なら現役参加者。
    # 離脱時点のスコアで凍結され、以降の得点は増えない。
    left_at = models.DateTimeField(null=True, blank=True)
    # AI が代役として入った参加者にだけ設定するランク帯（強さの決定に使う）。
    # 固定UUIDでAIを判別していた旧方式をやめ、参加者ごとに持たせる
    # （なりすまし用に毎回別人格のプロフィールを作るため）。
    ai_tier = models.CharField(max_length=4, blank=True, default="")
    # 対戦の体力。100%から始まり、0になった時点で敗北。
    hp = models.IntegerField(default=100)

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
    # このラウンドの決着内容 {"damage": {profile_id: 受けた%}, "reason": "..."}。
    # 攻撃演出（相手の画面を赤くする等）に使うため、結果を残しておく。
    outcome = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "対戦ラウンド"
        verbose_name_plural = "対戦ラウンド"
        unique_together = ("room", "round_number")
        ordering = ["round_number"]

    def __str__(self):
        return f"{self.room_id} R{self.round_number}"


class BattleBuzz(models.Model):
    """1ラウンドの解答 record。

    早押し制だった名残でモデル名は Buzz のままだが、現在は「選択肢を選んで
    回答した」記録として使う。``buzzed_at`` はサーバ時刻で、両者正解時に
    どちらが遅かったか（＝10%被弾する側）の判定に使う。``rank`` は解答した
    順番。クライアントのタイムスタンプは一切信用しない。
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


class MatchmakingTicket(models.Model):
    """クイックマッチの待機列 (spec: 同ランク優先、1分でAI対戦フォールバック)。

    POST /battle/quickmatch/ で作成 → 同条件で待機中の他ユーザーを探す →
    見つかればその場でルームを作成/開始する。見つからない間は
    GET /battle/quickmatch/{id}/ のポーリングごとに再探索し、作成から
    MATCH_TIMEOUT_SECONDS 経過していたら AI 対戦相手でルームを作る。
    """

    class Status(models.TextChoices):
        WAITING = "waiting", "対戦相手を探索中"
        MATCHED = "matched", "マッチ成立（人間）"
        AI_MATCHED = "ai_matched", "マッチ成立（AI）"
        CANCELLED = "cancelled", "キャンセル"

    user = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="matchmaking_tickets"
    )
    question_count = models.PositiveSmallIntegerField(default=10)
    tier_snapshot = models.CharField(
        max_length=4, blank=True, help_text="発行時点のランク（SS/S/A/B/C/D、未ランクは空）"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    room = models.ForeignKey(
        BattleRoom, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "マッチメイキング待機"
        verbose_name_plural = "マッチメイキング待機"
        indexes = [models.Index(fields=["status", "question_count", "created_at"])]

    def __str__(self):
        return f"{self.user_id} {self.status} ({self.tier_snapshot or '未ランク'})"
