from django.urls import path

from .views import DailyGoalView, HabitTodayView

urlpatterns = [
    path("today/", HabitTodayView.as_view(), name="habit-today"),
    path("goal/", DailyGoalView.as_view(), name="daily-goal"),
]
