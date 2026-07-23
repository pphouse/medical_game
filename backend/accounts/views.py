from django.conf import settings
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import NotificationPreference, PushSubscription, University
from .serializers import ProfileSerializer, UniversitySerializer


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
