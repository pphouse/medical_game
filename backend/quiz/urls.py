from django.urls import path

from .views import (
    CategoryListView,
    CategoryProgressView,
    HomeSummaryView,
    MyQuestionsView,
    QuestionDetailView,
    QuestionListView,
    QuestionReportView,
    QuestionSubmitForReviewView,
    ReviewActionView,
    ReviewDeckSummaryView,
    ReviewDeckView,
    ReviewQueueView,
    SubmitAnswerView,
    SubmitMasteryView,
)
from .views_review_filter import ReviewFilterView

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("progress/", CategoryProgressView.as_view(), name="category-progress"),
    path("summary/", HomeSummaryView.as_view(), name="home-summary"),
    path("questions/", QuestionListView.as_view(), name="question-list"),
    path("questions/<int:question_id>/", QuestionDetailView.as_view(), name="question-detail"),
    path(
        "questions/<int:question_id>/submit/",
        QuestionSubmitForReviewView.as_view(),
        name="question-submit-review",
    ),
    path(
        "questions/<int:question_id>/report/",
        QuestionReportView.as_view(),
        name="question-report",
    ),
    path("my-questions/", MyQuestionsView.as_view(), name="my-questions"),
    path("review-deck/", ReviewDeckView.as_view(), name="review-deck"),
    # 科目・評価・演習回数で絞り込んで演習セットを作る（復習デッキとは別物）。
    path("review-filter/", ReviewFilterView.as_view(), name="review-filter"),
    path("review-deck/summary/", ReviewDeckSummaryView.as_view(), name="review-deck-summary"),
    path("answers/", SubmitAnswerView.as_view(), name="submit-answer"),
    path(
        "answers/<int:answer_history_id>/mastery/",
        SubmitMasteryView.as_view(),
        name="submit-mastery",
    ),
    # moderation (spec 2-4: 人手レビューゲート)
    path("review/questions/", ReviewQueueView.as_view(), name="review-queue"),
    path(
        "review/questions/<int:question_id>/<str:action>/",
        ReviewActionView.as_view(),
        name="review-action",
    ),
]
