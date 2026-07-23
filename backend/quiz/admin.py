from django.contrib import admin
from django.utils import timezone

from .models import (
    AnswerHistory,
    CBTBlueprint,
    Question,
    QuestionReport,
    QuestionSet,
    ReviewSchedule,
)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """審査フロー (spec 2-4): status=pending を絞り込み、内容を確認の上で
    承認/却下する。LLM 生成問題（source=llm）を無審査で公開してはならない —
    医学的正確性の最終判断は必ず人間が行うこと。

    注: admin 経由の承認では reviewed_by (Profile FK) は空のまま
    （操作者は accounts.User のため）。レビュー者を記録する場合は
    moderator ロールのユーザーで API (/api/quiz/review/...) を使う。
    """

    list_display = (
        "id",
        "category",
        "question_type",
        "exam_type",
        "status",
        "source",
        "visibility",
        "blueprint_code",
        "answer_count",
        "correct_rate",
    )
    list_filter = ("status", "source", "question_type", "category", "exam_type", "visibility")
    search_fields = ("question_text", "explanation", "blueprint_code")
    actions = ["approve_questions", "reject_questions"]

    @admin.action(description="選択した問題を承認して公開する（内容確認済みのもののみ）")
    def approve_questions(self, request, queryset):
        updated = queryset.update(
            status=Question.Status.PUBLISHED, reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated}問を公開しました。")

    @admin.action(description="選択した問題を却下する")
    def reject_questions(self, request, queryset):
        updated = queryset.update(
            status=Question.Status.REJECTED, reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated}問を却下しました。")


@admin.register(QuestionSet)
class QuestionSetAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "blueprint_code", "status", "source", "created_at")
    list_filter = ("status", "source")
    search_fields = ("title", "case_stem")


@admin.register(CBTBlueprint)
class CBTBlueprintAdmin(admin.ModelAdmin):
    list_display = ("code", "area", "area_title", "subsection_title", "depth", "class_group")
    list_filter = ("section", "area", "class_group")
    search_fields = ("code", "subsection_title", "objective_text")


@admin.register(QuestionReport)
class QuestionReportAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "reporter", "reason", "created_at", "resolved_at")
    list_filter = ("reason",)


@admin.register(AnswerHistory)
class AnswerHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "question", "correct", "mastery_level", "answered_at")
    list_filter = ("correct", "mastery_level")


@admin.register(ReviewSchedule)
class ReviewScheduleAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "question", "next_review_at", "interval_days", "ease_factor")
