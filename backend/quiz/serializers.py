from rest_framework import serializers

from .models import AnswerHistory, Question, QuestionReport, ReviewSchedule


class QuestionSerializer(serializers.ModelSerializer):
    """Used for practice: intentionally omits correct_choice_key and
    explanation so the client can't see the answer before submitting."""

    mastery_level = serializers.SerializerMethodField()
    correct_rate = serializers.SerializerMethodField()
    case_stem = serializers.SerializerMethodField()
    last_correct = serializers.SerializerMethodField()
    last_response_time_ms = serializers.SerializerMethodField()
    last_answered_at = serializers.SerializerMethodField()

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
            "last_correct",
            "last_response_time_ms",
            "last_answered_at",
        ]

    def _last_history(self, obj):
        return self.context.get("history_by_question", {}).get(obj.id)

    def get_mastery_level(self, obj):
        row = self._last_history(obj)
        return row.mastery_level if row else "unstudied"

    def get_correct_rate(self, obj):
        # null until answer_count >= 10 (spec 2.1: 少数解答での誤解を避ける)
        return obj.public_correct_rate

    def get_last_correct(self, obj):
        row = self._last_history(obj)
        return row.correct if row else None

    def get_last_response_time_ms(self, obj):
        row = self._last_history(obj)
        return row.response_time_ms if row else None

    def get_last_answered_at(self, obj):
        row = self._last_history(obj)
        return row.answered_at if row else None

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
    # 「9/225問」のように実数で見せるため、割合だけでなく分子と分母も返す。
    answered_count = serializers.IntegerField()
    total_questions = serializers.IntegerField()
    university_rank = RankSerializer()
    national_rank = RankSerializer()


class SubmitAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_choice_key = serializers.CharField(max_length=4)
    response_time_ms = serializers.IntegerField(min_value=0)
    # クライアントが指定できるのは solo / review のみ。battle / mock は
    # それぞれのサーバフローでのみ記録される (spec フェーズ4)。
    context = serializers.ChoiceField(
        choices=[AnswerHistory.Context.SOLO, AnswerHistory.Context.REVIEW],
        default=AnswerHistory.Context.SOLO,
    )


class SubmitMasterySerializer(serializers.Serializer):
    mastery_level = serializers.ChoiceField(choices=AnswerHistory.MasteryLevel.choices)


VALID_CHOICE_KEYS = ["A", "B", "C", "D", "E"]


class UserQuestionSerializer(serializers.ModelSerializer):
    """ユーザー投稿問題の作成/編集 (spec フェーズ7).

    university はクライアント指定を信用せず、visibility=university_only の
    場合に作成者の所属で強制上書きする（ビュー側で設定）。
    """

    # 本文は必須。理由は AdminQuestionSerializer 側のコメントと同じ。
    question_text = serializers.CharField(allow_blank=False, trim_whitespace=True)

    class Meta:
        model = Question
        fields = [
            "id",
            "category",
            "topic",
            "exam_type",
            "difficulty",
            "question_text",
            "choices",
            "correct_choice_key",
            "explanation",
            "visibility",
            "status",
            "answer_count",
            "created_at",
        ]
        read_only_fields = ["id", "status", "answer_count", "created_at"]

    def validate_choices(self, value):
        if not isinstance(value, list) or len(value) != 5:
            raise serializers.ValidationError("選択肢はA〜Eの5個が必要です。")
        keys = []
        for choice in value:
            if not isinstance(choice, dict) or set(choice.keys()) != {"key", "text"}:
                raise serializers.ValidationError('各選択肢は {"key","text"} 形式です。')
            if choice["key"] not in VALID_CHOICE_KEYS:
                raise serializers.ValidationError("選択肢キーはA〜Eのみ。")
            if not str(choice["text"]).strip():
                raise serializers.ValidationError("選択肢テキストが空です。")
            keys.append(choice["key"])
        if sorted(keys) != VALID_CHOICE_KEYS:
            raise serializers.ValidationError("選択肢キーはA〜Eを1つずつ。")
        texts = [c["text"] for c in value]
        if len(set(texts)) != len(texts):
            raise serializers.ValidationError("選択肢テキストが重複しています。")
        return value

    def validate(self, attrs):
        choices = attrs.get("choices", getattr(self.instance, "choices", None))
        correct = attrs.get(
            "correct_choice_key", getattr(self.instance, "correct_choice_key", None)
        )
        if choices and correct not in [c["key"] for c in choices]:
            raise serializers.ValidationError(
                {"correct_choice_key": "正解キーが選択肢に存在しません。"}
            )
        return attrs


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
