from django.urls import path

from .views import DemoLoginView, MeView, UniversityListView

urlpatterns = [
    path("demo-login/", DemoLoginView.as_view(), name="demo-login"),
    path("me/", MeView.as_view(), name="me"),
    path("universities/", UniversityListView.as_view(), name="university-list"),
]
