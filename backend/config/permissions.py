from rest_framework.permissions import BasePermission


class IsModerator(BasePermission):
    message = "モデレーター権限が必要です。"

    def has_permission(self, request, view):
        return bool(getattr(request.user, "is_moderator", False))


class IsStudentVerified(BasePermission):
    message = "学生証認証が必要です。"

    def has_permission(self, request, view):
        return bool(getattr(request.user, "student_verified", False))
