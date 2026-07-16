from django.contrib import admin

from .models import MockExam, MockQuestion, MockResult, MonthlyRanking


@admin.register(MockExam)
class MockExamAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "start_at", "end_at")


@admin.register(MockQuestion)
class MockQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "mock_exam", "question", "order")


@admin.register(MockResult)
class MockResultAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "mock_exam", "score", "rank")


@admin.register(MonthlyRanking)
class MonthlyRankingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "university", "month", "questions_solved", "correct_rate")
