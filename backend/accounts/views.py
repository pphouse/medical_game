import uuid

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsModerator

from .models import (
    NotificationPreference,
    PushSubscription,
    StudentVerification,
    University,
)
from .serializers import ProfileSerializer, UniversitySerializer
from .storage import (
    create_signed_upload_url,
    create_signed_view_url,
    delete_student_id_image,
)


class UniversityListView(APIView):
    """List all universities (used by the profile-setup university picker)."""

    def get(self, request):
        universities = University.objects.order_by("name")
        return Response(UniversitySerializer(universities, many=True).data)


class BootstrapView(APIView):
    """First call after a Supabase sign-in.

    ``SupabaseJWTAuthentication`` has already auto-provisioned the Profile
    from the verified JWT, so this simply (optionally) applies the initial
    display_name/university/grade the client collected at sign-up, and
    returns the profile.
    """

    def post(self, request):
        serializer = ProfileSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MeView(APIView):
    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class NotificationPreferenceView(APIView):
    """復習リマインドの設定 (spec フェーズ6)。オプトイン既定 off。"""

    def _payload(self, pref):
        return {
            "enabled": pref.enabled,
            "preferred_hour": pref.preferred_hour,
            "timezone": pref.timezone,
            "vapid_public_key": settings.VAPID_PUBLIC_KEY or None,
        }

    def get(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(profile=request.user)
        return Response(self._payload(pref))

    def patch(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(profile=request.user)
        if "enabled" in request.data:
            pref.enabled = bool(request.data["enabled"])
        if "preferred_hour" in request.data:
            hour = int(request.data["preferred_hour"])
            if not 0 <= hour <= 23:
                raise exceptions.ValidationError("preferred_hour は 0〜23")
            pref.preferred_hour = hour
        if "timezone" in request.data:
            import zoneinfo

            tz = str(request.data["timezone"])
            try:
                zoneinfo.ZoneInfo(tz)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                raise exceptions.ValidationError("不正なタイムゾーンです") from None
            pref.timezone = tz
        pref.save()
        return Response(self._payload(pref))


def verification_payload(verification):
    return {
        "id": verification.id,
        "status": verification.status,
        "university_id": verification.university_id,
        "university": verification.university.name if verification.university else None,
        "submitted_at": verification.submitted_at,
        "reject_reason": verification.reject_reason or None,
        "created_at": verification.created_at,
    }


class StudentVerificationView(APIView):
    """学生証認証の申請 (spec フェーズ7).

    POST は Storage の private bucket への **signed upload URL** を返す
    （画像そのものを Django 経由で受けない）。アップロード完了後に
    PATCH .../{id}/complete/ で status=pending にする。
    """

    def get(self, request):
        verification = (
            request.user.student_verifications.order_by("-created_at")
            .select_related("university")
            .first()
        )
        return Response(
            {
                "student_verified": request.user.student_verified,
                "latest": verification_payload(verification) if verification else None,
            }
        )

    def post(self, request):
        if request.user.student_verified:
            raise exceptions.ValidationError("すでに学生証認証済みです。")
        if request.user.student_verifications.filter(
            status=StudentVerification.Status.PENDING
        ).exists():
            raise exceptions.ValidationError("審査中の申請があります。")
        # アップロード未完了の draft が残っていると永久に再申請できなくなる
        # ので、破棄してやり直せるようにする（画像が上がっていれば削除）。
        for stale in request.user.student_verifications.filter(
            status=StudentVerification.Status.DRAFT
        ):
            delete_student_id_image(stale.image_path)
            stale.delete()

        university_id = request.data.get("university_id")
        if not university_id:
            raise exceptions.ValidationError("university_id は必須です。")
        university = get_object_or_404(University, pk=university_id)

        object_path = f"{request.user.id}/{uuid.uuid4().hex}.jpg"
        upload = create_signed_upload_url(object_path)
        verification = StudentVerification.objects.create(
            profile=request.user,
            university=university,
            image_path=object_path,
        )
        return Response(
            {"verification": verification_payload(verification), "upload": upload},
            status=201,
        )


class StudentVerificationCompleteView(APIView):
    def patch(self, request, verification_id):
        verification = get_object_or_404(
            StudentVerification, pk=verification_id, profile=request.user
        )
        if verification.status != StudentVerification.Status.DRAFT:
            raise exceptions.ValidationError("この申請はアップロード待ちではありません。")
        verification.status = StudentVerification.Status.PENDING
        verification.submitted_at = timezone.now()
        verification.save(update_fields=["status", "submitted_at"])
        return Response(verification_payload(verification))


class StudentVerificationReviewQueueView(APIView):
    """審査待ち一覧（moderator）。画像はレビュー時のみ5分の signed URL。"""

    permission_classes = [IsModerator]

    def get(self, request):
        rows = []
        pending = (
            StudentVerification.objects.filter(
                status=StudentVerification.Status.PENDING
            )
            .select_related("profile", "university")
            .order_by("submitted_at")[:100]
        )
        for verification in pending:
            payload = verification_payload(verification)
            payload["display_name"] = verification.profile.display_name or "匿名ユーザー"
            payload["image_url"] = create_signed_view_url(verification.image_path)
            rows.append(payload)
        return Response(rows)


class StudentVerificationDecisionView(APIView):
    permission_classes = [IsModerator]

    def post(self, request, verification_id, action):
        if action not in ("approve", "reject"):
            raise exceptions.ValidationError("action は approve / reject のみ")
        verification = get_object_or_404(StudentVerification, pk=verification_id)
        if verification.status != StudentVerification.Status.PENDING:
            raise exceptions.ValidationError("審査待ちではありません。")
        if action == "approve":
            verification.approve(reviewed_by=request.user)
        else:
            verification.reject(
                reason=request.data.get("reason", ""), reviewed_by=request.user
            )
        return Response(verification_payload(verification))


class PushSubscriptionView(APIView):
    """ブラウザの PushSubscription を登録/解除する (spec フェーズ6)."""

    def post(self, request):
        endpoint = request.data.get("endpoint")
        keys = request.data.get("keys")
        if not endpoint or not isinstance(keys, dict) or "p256dh" not in keys:
            raise exceptions.ValidationError("endpoint と keys(p256dh, auth) が必要です")
        PushSubscription.objects.update_or_create(
            endpoint=endpoint, defaults={"profile": request.user, "keys": keys}
        )
        return Response({"registered": True}, status=201)

    def delete(self, request):
        endpoint = request.data.get("endpoint")
        deleted, _ = PushSubscription.objects.filter(
            profile=request.user, endpoint=endpoint
        ).delete()
        return Response({"deleted": bool(deleted)})
