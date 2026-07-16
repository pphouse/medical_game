from django.contrib import admin

from .models import AnswerHistory, Question, ReviewSchedule


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "exam_type", "difficulty", "visibility", "correct_rate")
    list_filter = ("category", "exam_type", "difficulty", "visibility")
    search_fields = ("explanation",)


@admin.register(AnswerHistory)
class AnswerHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "question", "correct", "mastery_level", "answered_at")
    list_filter = ("correct", "mastery_level")


@admin.register(ReviewSchedule)
class ReviewScheduleAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "question", "next_review_at", "interval_days", "ease_factor")
