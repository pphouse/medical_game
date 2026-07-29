from django.urls import path

from .views import (
    BootstrapView,
    MeView,
    NotificationPreferenceView,
    PushSubscriptionView,
    StudentVerificationCompleteView,
    StudentVerificationDecisionView,
    StudentVerificationReviewQueueView,
    StudentVerificationView,
    UniversityListView,
)

urlpatterns = [
    path("bootstrap/", BootstrapView.as_view(), name="auth-bootstrap"),
    path("me/", MeView.as_view(), name="me"),
    path("universities/", UniversityListView.as_view(), name="university-list"),
    path("notifications/", NotificationPreferenceView.as_view(), name="notification-preference"),
    path("push-subscriptions/", PushSubscriptionView.as_view(), name="push-subscriptions"),
    # 学生証認証 (spec フェーズ7)
    path("student-verification/", StudentVerificationView.as_view(), name="student-verification"),
    path(
        "student-verification/<int:verification_id>/complete/",
        StudentVerificationCompleteView.as_view(),
        name="student-verification-complete",
    ),
    path(
        "student-verification/pending/",
        StudentVerificationReviewQueueView.as_view(),
        name="student-verification-queue",
    ),
    path(
        "student-verification/<int:verification_id>/<str:action>/",
        StudentVerificationDecisionView.as_view(),
        name="student-verification-decision",
    ),
]
