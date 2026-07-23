from rest_framework import serializers

from .models import AnswerHistory, Question, QuestionReport, ReviewSchedule


class QuestionSerializer(serializers.ModelSerializer):
    """Used for practice: intentionally omits correct_choice_key and
    explanation so the client can't see the answer before submitting."""

    mastery_level = serializers.SerializerMethodField()
    correct_rate = serializers.SerializerMethodField()
    case_stem = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id",
            "category",
            "topic",
            "difficulty",
            "exam_type",
            "question_type",
            "blueprint_code",
            "question_set_id",
            "set_order",
            "case_stem",
            "question_text",
            "choices",
            "correct_rate",
            "mastery_level",
        ]

    def get_mastery_level(self, obj):
        mastery_by_question = self.context.get("mastery_by_question", {})
        return mastery_by_question.get(obj.id, "unstudied")

    def get_correct_rate(self, obj):
        # null until answer_count >= 10 (spec 2.1: 少数解答での誤解を避ける)
        return obj.public_correct_rate

    def get_case_stem(self, obj):
        if obj.question_set_id:
            return obj.question_set.case_stem
        return None


class ReviewQuestionSerializer(serializers.ModelSerializer):
    """Moderator-only: includes the answer and review metadata."""

    case_stem = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id",
            "category",
            "topic",
            "difficulty",
            "exam_type",
            "question_type",
            "blueprint_code",
            "class_group",
            "question_set_id",
            "set_order",
            "case_stem",
            "question_text",
            "choices",
            "correct_choice_key",
            "explanation",
            "status",
            "source",
            "visibility",
            "reviewed_by",
            "reviewed_at",
            "created_at",
        ]

    def get_case_stem(self, obj):
        if obj.question_set_id:
            return obj.question_set.case_stem
        return None


class CategorySerializer(serializers.Serializer):
    category = serializers.CharField()
    count = serializers.IntegerField()


class MasteryCountsSerializer(serializers.Serializer):
    double_circle = serializers.IntegerField()
    circle = serializers.IntegerField()
    triangle = serializers.IntegerField()
    cross = serializers.IntegerField()
    unstudied = serializers.IntegerField()


class CategoryProgressSerializer(serializers.Serializer):
    category = serializers.CharField()
    total = serializers.IntegerField()
    remaining = serializers.IntegerField()
    counts = MasteryCountsSerializer()


class RankSerializer(serializers.Serializer):
    rank = serializers.IntegerField(allow_null=True)
    out_of = serializers.IntegerField()


class HomeSummarySerializer(serializers.Serializer):
    overall_progress_pct = serializers.FloatField()
    overall_correct_rate = serializers.FloatField()
    university_rank = RankSerializer()
    national_rank = RankSerializer()


class SubmitAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_choice_key = serializers.CharField(max_length=4)
    response_time_ms = serializers.IntegerField(min_value=0)


class SubmitMasterySerializer(serializers.Serializer):
    mastery_level = serializers.ChoiceField(choices=AnswerHistory.MasteryLevel.choices)


class QuestionReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionReport
        fields = ["id", "question", "reason", "detail", "created_at"]
        read_only_fields = ["id", "question", "created_at"]


class ReviewScheduleSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)

    class Meta:
        model = ReviewSchedule
        fields = ["question", "next_review_at", "interval_days", "ease_factor"]
