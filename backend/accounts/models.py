from django.contrib.auth.models import AbstractUser
from django.db import models


class University(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name = "大学"
        verbose_name_plural = "大学"

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Django admin staff accounts ONLY.

    Since the Supabase Auth migration (phase 0), end users are represented
    by ``Profile`` (keyed by ``auth.users.id``); no app-level FK points at
    this model anymore and API requests never authenticate as it.
    """

    university = models.ForeignKey(
        University,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    student_verified = models.BooleanField(default=False)
    email = models.EmailField(unique=True)
    grade = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="学年（医学部は1〜6年）"
    )

    def __str__(self):
        return self.username


class Profile(models.Model):
    """App-level user profile, 1:1 with Supabase ``auth.users``.

    The PK is the Supabase user UUID (JWT ``sub`` claim). Rows are
    auto-provisioned by ``SupabaseJWTAuthentication`` on first API access,
    so a valid access token is always enough to act as a user. Returned as
    ``request.user`` in DRF views.
    """

    class Role(models.TextChoices):
        STUDENT = "student", "学生"
        MODERATOR = "moderator", "モデレーター"
        ADMIN = "admin", "管理者"

    class ExamPreference(models.TextChoices):
        """演習・模試で既定にする試験種別。

        空文字は「未選択」で、学年から自動で決める（4年生以下は CBT、
        5年生以降は国試）。学年は毎年4月1日のバッチで繰り上がるので、
        未選択のままにしておけば進級に追従する。明示的に選んだ場合は
        そちらを優先し、進級しても勝手に変わらない。
        """

        AUTO = "", "学年に合わせる"
        CBT = "CBT", "CBT"
        KOKUSHI = "KOKUSHI", "医師国家試験"

    id = models.UUIDField(primary_key=True, editable=False)
    display_name = models.CharField(max_length=50, blank=True)
    university = models.ForeignKey(
        University,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profiles",
    )
    grade = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="学年（医学部は1〜6年）"
    )
    student_verified = models.BooleanField(default=False)
    exam_preference = models.CharField(
        max_length=10,
        choices=ExamPreference.choices,
        blank=True,
        default=ExamPreference.AUTO,
        help_text="演習・模試の既定の試験種別。未選択なら学年から決める。",
    )
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.STUDENT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # 対戦＋模試（週次/月次）合算のランクポイント (spec: SS/S/A/B/C/D)。
    # 1000 を基準値とし、勝敗・成績に応じて増減する。
    points = models.IntegerField(default=1000)
    ranked_matches = models.PositiveIntegerField(
        default=0, help_text="ポイントが確定した対戦・模試の回数（ランク算出の母集団判定に使う）"
    )
    # 対戦のマッチメイキングで人が見つからない場合に充てる AI 対戦相手のフラグ。
    # ランキング集計・ポイント分布からは常に除外する。
    is_ai = models.BooleanField(default=False)

    # Duck-typing for DRF's IsAuthenticated / throttling, mirroring
    # django.contrib.auth model attributes.
    is_authenticated = True
    is_anonymous = False
    is_active = True

    class Meta:
        verbose_name = "プロフィール"
        verbose_name_plural = "プロフィール"

    def __str__(self):
        return self.display_name or str(self.id)

    @property
    def is_moderator(self):
        return self.role in (self.Role.MODERATOR, self.Role.ADMIN)

    # 学年から試験種別を決める境目。4年生以下は CBT、5年生以降は国試。
    CBT_MAX_GRADE = 4

    @property
    def resolved_exam_type(self):
        """実際に使う試験種別。明示的な選択があればそれ、無ければ学年から。

        学年も未設定なら CBT にする。学年を入れていない利用者は入学直後か
        設定を飛ばした人で、国試より CBT の方が当たりやすい。
        """
        if self.exam_preference:
            return self.exam_preference
        if self.grade is None:
            return self.ExamPreference.CBT
        return (
            self.ExamPreference.CBT
            if self.grade <= self.CBT_MAX_GRADE
            else self.ExamPreference.KOKUSHI
        )


class StudentVerification(models.Model):
    """学生証審査 (spec 2.2 / フェーズ7).

    画像そのものは private バケット (settings.STUDENT_ID_BUCKET) にあり、
    Django はパスだけを保持する。アップロードは signed upload URL 経由
    （画像を Django で受けない）。レビュー時のみ短期 signed URL を発行。

    保持期間の最小化 (spec): 却下時は即削除、承認後は
    STUDENT_ID_RETENTION_DAYS (90日) で cleanup_student_id_images が削除。
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "アップロード待ち"
        PENDING = "pending", "審査待ち"
        APPROVED = "approved", "承認"
        REJECTED = "rejected", "却下"

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="student_verifications"
    )
    university = models.ForeignKey(
        University,
        on_delete=models.SET_NULL,
        null=True,
        help_text="申請時に本人が選択。承認時に Profile.university に確定される",
    )
    image_path = models.CharField(max_length=500, help_text="バケット内のオブジェクトパス")
    image_deleted_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    reviewed_by = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_student_verifications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "学生証審査"
        verbose_name_plural = "学生証審査"

    def __str__(self):
        return f"{self.profile_id} - {self.status}"

    def approve(self, reviewed_by=None):
        """承認: Profile.student_verified=True + university 確定 (spec フェーズ7)."""
        from django.utils import timezone

        self.status = self.Status.APPROVED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        self.profile.student_verified = True
        if self.university_id:
            self.profile.university_id = self.university_id
        self.profile.save(update_fields=["student_verified", "university"])

    def reject(self, reason="", reviewed_by=None):
        """却下: 画像を即削除する (spec フェーズ7)."""
        from django.utils import timezone

        from .storage import delete_student_id_image

        self.status = self.Status.REJECTED
        self.reject_reason = reason
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reject_reason", "reviewed_by", "reviewed_at"])
        if delete_student_id_image(self.image_path):
            self.image_deleted_at = timezone.now()
            self.save(update_fields=["image_deleted_at"])


class PushSubscription(models.Model):
    """Web Push (VAPID) の購読情報 (spec フェーズ6)."""

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.TextField(unique=True)
    keys = models.JSONField(help_text='{"p256dh": "...", "auth": "..."}')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Push購読"
        verbose_name_plural = "Push購読"

    def __str__(self):
        return f"{self.profile_id} {self.endpoint[:40]}"


class NotificationPreference(models.Model):
    """復習リマインドのユーザー設定。**オプトインは既定 off** (spec フェーズ6)."""

    profile = models.OneToOneField(
        Profile, on_delete=models.CASCADE, related_name="notification_preference"
    )
    enabled = models.BooleanField(default=False)
    preferred_hour = models.PositiveSmallIntegerField(
        default=20, help_text="通知を送る時刻（0〜23, ユーザーのタイムゾーン基準）"
    )
    timezone = models.CharField(max_length=50, default="Asia/Tokyo")

    class Meta:
        verbose_name = "通知設定"
        verbose_name_plural = "通知設定"

    def __str__(self):
        return f"{self.profile_id} enabled={self.enabled} {self.preferred_hour}時"
