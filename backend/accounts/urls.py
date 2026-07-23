from django.urls import path

from .views import (
    BootstrapView,
    MeView,
    NotificationPreferenceView,
    PushSubscriptionView,
    UniversityListView,
)

urlpatterns = [
    path("bootstrap/", BootstrapView.as_view(), name="auth-bootstrap"),
    path("me/", MeView.as_view(), name="me"),
    path("universities/", UniversityListView.as_view(), name="university-list"),
    path("notifications/", NotificationPreferenceView.as_view(), name="notification-preference"),
    path("push-subscriptions/", PushSubscriptionView.as_view(), name="push-subscriptions"),
]
