from django.urls import path

from .admin_views import (
    AdminBulkStatusView,
    AdminQuestionDetailView,
    AdminQuestionListView,
    AdminReportListView,
    AdminStatsView,
    AdminUserListView,
)

urlpatterns = [
    path("stats/", AdminStatsView.as_view(), name="admin-stats"),
    path("questions/", AdminQuestionListView.as_view(), name="admin-question-list"),
    path(
        "questions/<int:question_id>/",
        AdminQuestionDetailView.as_view(),
        name="admin-question-detail",
    ),
    path("questions/bulk-status/", AdminBulkStatusView.as_view(), name="admin-bulk-status"),
    path("reports/", AdminReportListView.as_view(), name="admin-report-list"),
    path("users/", AdminUserListView.as_view(), name="admin-user-list"),
]
