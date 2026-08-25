from rest_framework import serializers

from .models import Profile, University


class UniversitySerializer(serializers.ModelSerializer):
    class Meta:
        model = University
        fields = ["id", "name"]


class ProfileSerializer(serializers.ModelSerializer):
    """Never expose the email address here: ランキング等で他ユーザーにも
    渡り得るため、メールアドレスは API に一切載せない (spec フェーズ3)."""

    university = UniversitySerializer(read_only=True)
    university_id = serializers.PrimaryKeyRelatedField(
        queryset=University.objects.all(),
        source="university",
        write_only=True,
        required=False,
        allow_null=True,
    )

    # 未選択("")のときに学年から決まる実効値。フロントはこれを既定タブに使う。
    resolved_exam_type = serializers.CharField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            "id",
            "display_name",
            "university",
            "university_id",
            "grade",
            "exam_preference",
            "resolved_exam_type",
            "student_verified",
            "role",
        ]
        read_only_fields = ["id", "student_verified", "role", "resolved_exam_type"]

    def validate_grade(self, value):
        if value is not None and not 1 <= value <= 6:
            raise serializers.ValidationError("学年は1〜6で指定してください。")
        return value
