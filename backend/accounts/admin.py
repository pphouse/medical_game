from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.html import format_html

from .models import (
    NotificationPreference,
    Profile,
    PushSubscription,
    StudentVerification,
    University,
    User,
)
from .storage import create_signed_view_url


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "university", "grade", "student_verified", "role")
    list_filter = ("university", "student_verified", "role")
    search_fields = ("display_name", "id")


@admin.register(StudentVerification)
class StudentVerificationAdmin(admin.ModelAdmin):
    """学生証審査 (spec フェーズ7)。画像はレビュー時のみ5分間の signed URL。
    承認で Profile.student_verified=True + 大学確定、却下で画像即削除。"""

    list_display = ("id", "profile", "university", "status", "submitted_at", "reviewed_at")
    list_filter = ("status",)
    readonly_fields = ("image_link", "image_path", "profile", "created_at")
    actions = ["approve_selected", "reject_selected"]

    @admin.display(description="学生証画像（5分間有効）")
    def image_link(self, obj):
        url = create_signed_view_url(obj.image_path)
        if not url:
            return "（Storage未設定 or 画像削除済み）"
        return format_html('<a href="{}" target="_blank" rel="noopener">画像を開く</a>', url)

    @admin.action(description="選択した申請を承認する（本人確認済みのもののみ）")
    def approve_selected(self, request, queryset):
        count = 0
        for verification in queryset.filter(status=StudentVerification.Status.PENDING):
            verification.approve()
            count += 1
        self.message_user(request, f"{count}件を承認しました。")

    @admin.action(description="選択した申請を却下する（画像は即削除）")
    def reject_selected(self, request, queryset):
        count = 0
        for verification in queryset.filter(status=StudentVerification.Status.PENDING):
            verification.reject(reason="管理画面で却下")
            count += 1
        self.message_user(request, f"{count}件を却下しました。")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("profile", "enabled", "preferred_hour", "timezone")


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("profile", "endpoint", "created_at")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("大学連携", {"fields": ("university", "student_verified")}),
    )
    list_display = ("username", "email", "university", "student_verified", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("university", "student_verified")
