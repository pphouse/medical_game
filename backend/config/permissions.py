from rest_framework.permissions import BasePermission


class IsModerator(BasePermission):
    message = "モデレーター権限が必要です。"

    def has_permission(self, request, view):
        return bool(getattr(request.user, "is_moderator", False))


class IsStudentVerified(BasePermission):
    message = "学生証認証が必要です。"

    def has_permission(self, request, view):
        return bool(getattr(request.user, "student_verified", False))


class IsAdmin(BasePermission):
    """role=admin だけ。moderator は含めない。

    IsModerator は moderator と admin の両方を通す（Profile.is_moderator）。
    ロール変更のようにモデレーター自身の権限を書き換えられる操作は、
    moderator に許すと権限昇格になるので admin 限定にする。
    """

    message = "管理者権限が必要です。"

    def has_permission(self, request, view):
        role = getattr(request.user, "role", None)
        return role == "admin"
