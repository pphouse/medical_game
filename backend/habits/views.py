from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.internal_auth import require_internal_caller

from .progress import MAX_GOAL, habit_payload, set_daily_goal
from .reminders import send_due_reminders


class HabitTodayView(APIView):
    """GET /api/habits/today/ — 今日の目標・進み具合・連続記録と、通知の予定。"""

    def get(self, request):
        return Response(habit_payload(request.user))


class DailyGoalSerializer(serializers.Serializer):
    questions_per_day = serializers.IntegerField(min_value=1, max_value=MAX_GOAL)


class DailyGoalView(APIView):
    """PUT /api/habits/goal/ — 1日の目標を決める・変える。

    今日の目標をもう達成してから上げた場合は明日から効く（effective_from）。
    """

    def put(self, request):
        payload = DailyGoalSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        effective_from = set_daily_goal(request.user, payload.validated_data["questions_per_day"])
        return Response({**habit_payload(request.user), "effective_from": effective_from})


class InternalSendRemindersView(APIView):
    """POST/GET /api/internal/send-reminders/ — 学習リマインドの Web Push（毎時）。

    ほかの内部エンドポイントと同じく、pg_cron（POST + X-Internal-Token）と
    Vercel Cron（GET + Authorization: Bearer CRON_SECRET）の両方から叩ける。
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """Vercel Cron は GET しか送れないので、POST と同じ処理を用意する。"""
        return self.post(request)

    def post(self, request):
        require_internal_caller(request)
        return Response({"status": "ok", "sent": send_due_reminders()})
