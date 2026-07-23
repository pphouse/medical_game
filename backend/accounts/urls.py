from django.urls import path

from .views import BootstrapView, MeView, UniversityListView

urlpatterns = [
    path("bootstrap/", BootstrapView.as_view(), name="auth-bootstrap"),
    path("me/", MeView.as_view(), name="me"),
    path("universities/", UniversityListView.as_view(), name="university-list"),
]
