from rest_framework.response import Response
from rest_framework.views import APIView

from .models import University
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
