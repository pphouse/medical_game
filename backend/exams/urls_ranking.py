from django.urls import path

from .views import ExamRankingHistoryView, RankingView

urlpatterns = [
    path("", RankingView.as_view(), name="ranking"),
    path("exams/", ExamRankingHistoryView.as_view(), name="ranking-exams"),
]
