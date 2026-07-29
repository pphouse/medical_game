from django.urls import path

from .views import (
    ExamAnswerView,
    ExamListView,
    ExamQuestionsView,
    ExamResultView,
    ExamStartView,
    ExamSubmitView,
)

urlpatterns = [
    path("", ExamListView.as_view(), name="exam-list"),
    path("<int:exam_id>/start/", ExamStartView.as_view(), name="exam-start"),
    path("<int:exam_id>/questions/", ExamQuestionsView.as_view(), name="exam-questions"),
    path("<int:exam_id>/answers/", ExamAnswerView.as_view(), name="exam-answers"),
    path("<int:exam_id>/submit/", ExamSubmitView.as_view(), name="exam-submit"),
    path("<int:exam_id>/result/", ExamResultView.as_view(), name="exam-result"),
]
