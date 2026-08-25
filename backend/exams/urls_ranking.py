from django.urls import path

from .views import ExamRankingHistoryView, PointsRankingView, RankingView
from .views_rank_detail import RankDetailView

urlpatterns = [
    path("", RankingView.as_view(), name="ranking"),
    path("exams/", ExamRankingHistoryView.as_view(), name="ranking-exams"),
    path("points/", PointsRankingView.as_view(), name="ranking-points"),
    # 順位クリック時の詳細（散布図・直近30日の演習数・昨日の演習状況）。
    path("detail/", RankDetailView.as_view(), name="ranking-detail"),
]
