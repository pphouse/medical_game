from django.contrib.auth import login
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import University, User
from .serializers import UniversitySerializer, UserSerializer


class UniversityListView(APIView):
    """List all universities (used by the future registration flow's
    university picker, per spec section 4: ユーザー登録・大学紐付け)."""

    permission_classes = [AllowAny]

    def get(self, request):
        universities = University.objects.order_by("name")
        return Response(UniversitySerializer(universities, many=True).data)


class DemoLoginView(APIView):
    """Demo-only shortcut: logs into the seeded demo account without a
    password so the quiz flow can be tried immediately.

    The real product flow (email verification + student ID review, per the
    spec) is out of scope for this phase-1 demo and would replace this view.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        university, _ = University.objects.get_or_create(name="サンプル医科大学")
        user, _ = User.objects.get_or_create(
            username="demo",
            defaults={
                "email": "demo@example.com",
                "first_name": "太郎",
                "last_name": "山田",
                "university": university,
                "student_verified": True,
                "grade": 4,
            },
        )
        login(request, user)
        return Response(UserSerializer(user).data)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
