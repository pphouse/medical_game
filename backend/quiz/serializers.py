from rest_framework import serializers

from .models import AnswerHistory, Question, ReviewSchedule


class QuestionSerializer(serializers.ModelSerializer):
    """Used for practice: intentionally omits correct_choice_key and
    explanation so the client can't see the answer before submitting."""

    mastery_level = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id",
            "category",
            "topic",
            "difficulty",
            "exam_type",
            "question_text",
            "choices",
            "correct_rate",
            "mastery_level",
        ]

    def get_mastery_level(self, obj):
        mastery_by_question = self.context.get("mastery_by_question", {})
        return mastery_by_question.get(obj.id, "unstudied")


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


class ReviewScheduleSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)

    class Meta:
        model = ReviewSchedule
        fields = ["question", "next_review_at", "interval_days", "ease_factor"]
