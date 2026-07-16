from django.urls import path

from .views import (
    CategoryListView,
    CategoryProgressView,
    HomeSummaryView,
    QuestionListView,
    ReviewDeckView,
    SubmitAnswerView,
    SubmitMasteryView,
)

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("progress/", CategoryProgressView.as_view(), name="category-progress"),
    path("summary/", HomeSummaryView.as_view(), name="home-summary"),
    path("questions/", QuestionListView.as_view(), name="question-list"),
    path("review-deck/", ReviewDeckView.as_view(), name="review-deck"),
    path("answers/", SubmitAnswerView.as_view(), name="submit-answer"),
    path(
        "answers/<int:answer_history_id>/mastery/",
        SubmitMasteryView.as_view(),
        name="submit-mastery",
    ),
]
