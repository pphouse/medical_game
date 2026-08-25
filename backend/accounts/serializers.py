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

    def validate_university_id(self, value):
        """所属大学は一度設定したら変更できない。

        学内ランキングの母集団が所属大学で決まるので、自由に付け替えられると
        順位を操作できてしまう。UI 側でも編集不可にしているが、API を直接
        叩かれても通らないようにここで拒否する。未設定からの初回設定
        （サインアップ直後の bootstrap）だけを許可する。

        フック名は source("university") ではなく宣言名("university_id")側で
        ないと DRF に呼ばれないので注意。
        """
        current = getattr(self.instance, "university_id", None)
        # null で一度消してから付け替える抜け道を塞ぐため、解除も拒否する。
        if current is not None and (value is None or value.pk != current):
            raise serializers.ValidationError(
                "所属大学は変更できません。変更が必要な場合はお問い合わせください。"
            )
        return value
