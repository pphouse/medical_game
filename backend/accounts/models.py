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
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.STUDENT
    )
    created_at = models.DateTimeField(auto_now_add=True)

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
