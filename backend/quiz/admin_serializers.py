"""管理画面用のシリアライザ。

学習者向けの QuestionSerializer は正答を隠すが、管理画面では正答も
status も編集させる必要がある。ユーザー投稿用の UserQuestionSerializer は
status を read_only にしているので（フェーズ7: 投稿者が自分で公開できると
審査ゲートが無意味になる）、管理側は別のシリアライザを持つ。
"""

from rest_framework import serializers

from .categories import canonicalize, is_canonical
from .models import Question, QuestionReport
from .serializers import VALID_CHOICE_KEYS


class AdminQuestionSerializer(serializers.ModelSerializer):
    """管理者による問題の作成・編集。status と visibility も直接指定できる。"""

    case_stem = serializers.SerializerMethodField()
    report_count = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id",
            "category",
            "topic",
            "exam_type",
            "difficulty",
            "question_type",
            "blueprint_code",
            "class_group",
            "question_text",
            "choices",
            "correct_choice_key",
            "explanation",
            "visibility",
            "status",
            "source",
            "question_set_id",
            "set_order",
            "case_stem",
            "answer_count",
            "correct_rate",
            "report_count",
            "reviewed_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "answer_count",
            "correct_rate",
            "report_count",
            "reviewed_at",
            "created_at",
            "question_set_id",
            "set_order",
            "case_stem",
        ]

    def get_case_stem(self, obj):
        return obj.question_set.case_stem if obj.question_set_id else None

    def get_report_count(self, obj):
        # 一覧では annotate 済みの値を使い、詳細では都度数える。
        annotated = getattr(obj, "annotated_report_count", None)
        return annotated if annotated is not None else obj.reports.count()

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

    def validate_category(self, value):
        """分野名は正典のものだけ通す。

        表記ゆれ（「循環器」→「循環器系」）は黙って直すのではなく、
        直した名前を示して弾く。管理画面はプルダウンで選ばせるので、
        ここに来る誤りは API 直叩きか正典の更新漏れであり、
        気づかせたほうがよい。
        """
        name = (value or "").strip()
        if is_canonical(name):
            return name
        fixed = canonicalize(name)
        if is_canonical(fixed):
            raise serializers.ValidationError(f"分野は「{fixed}」を指定してください。")
        raise serializers.ValidationError(f"「{name}」は登録された分野ではありません。")

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


class AdminReportSerializer(serializers.ModelSerializer):
    question_id = serializers.IntegerField(source="question.id", read_only=True)
    question_text = serializers.CharField(source="question.question_text", read_only=True)
    question_status = serializers.CharField(source="question.status", read_only=True)

    class Meta:
        model = QuestionReport
        fields = [
            "id",
            "question_id",
            "question_text",
            "question_status",
            "reason",
            "detail",
            "created_at",
        ]
