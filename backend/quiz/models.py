from django.db import models
from django.db.models import Q


class QuestionSet(models.Model):
    """タイプQ（順次解答四連問）の親。同一症例で 医療面接→身体診察→検査→
    病態生理/診断 の4問が set_order 順にぶら下がる (spec 2.2)."""

    title = models.CharField(max_length=255)
    blueprint_code = models.CharField(max_length=32, blank=True, db_index=True)
    case_stem = models.TextField(help_text="症例導入文")
    status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "下書き"),
            ("pending", "審査待ち"),
            ("published", "公開"),
            ("rejected", "却下"),
        ],
        default="draft",
    )
    source = models.CharField(
        max_length=20,
        choices=[("official", "公式"), ("llm", "LLM生成"), ("user", "ユーザー作成")],
        default="official",
    )
    creator = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_question_sets",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "四連問セット"
        verbose_name_plural = "四連問セット"

    def __str__(self):
        return f"[Q] {self.title}"


class CBTBlueprint(models.Model):
    """CBT 出題基準（令和7年版）の索引 (spec 3).

    著作権上の注意: `objective_text`（到達目標の原文）は問題生成プロンプト
    の内部用途に限定する。クライアントへ返す API では code / area_title /
    subsection_title（分野名レベル）のみ公開すること (spec 3.2-3)。
    """

    code = models.CharField(primary_key=True, max_length=32, help_text='例 "D-5-4)-(2)-③"')
    section = models.CharField(max_length=2, help_text="大区分 A〜F")
    area = models.CharField(max_length=8, db_index=True, help_text='例 "D-5"')
    area_title = models.CharField(max_length=100, help_text='例 "循環器系"')
    subsection_title = models.CharField(max_length=255, blank=True)
    objective_text = models.TextField(
        blank=True, help_text="到達目標の原文。生成プロンプト専用・API非公開"
    )
    depth = models.CharField(
        max_length=20, blank=True, help_text="説明できる / 概説できる / 列挙できる"
    )
    class_group = models.CharField(
        max_length=2, blank=True, choices=[("I", "Ⅰ群"), ("II", "Ⅱ群")]
    )
    disease_names = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "CBT出題基準"
        verbose_name_plural = "CBT出題基準"

    def __str__(self):
        return f"{self.code} {self.subsection_title or self.area_title}"


class QuestionQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Question.Status.PUBLISHED)

    def visible_to(self, profile):
        """演習に出してよい問題: published かつ (公開 or 同一大学の学内限定).

        学内限定は「同一大学かつ学生証認証済み」のみ (spec フェーズ7)。
        Django 側の防御。RLS 側にも同じ条件を実装する（多重防御）。
        """
        qs = self.published()
        if (
            profile is not None
            and getattr(profile, "student_verified", False)
            and profile.university_id
        ):
            return qs.filter(
                Q(visibility=Question.Visibility.PUBLIC)
                | Q(
                    visibility=Question.Visibility.UNIVERSITY_ONLY,
                    university_id=profile.university_id,
                )
            )
        return qs.filter(visibility=Question.Visibility.PUBLIC)


class Question(models.Model):
    """spec: Question: id, category, difficulty, exam_type, choices(JSON),
    explanation, creator_id(FK, null=official), visibility, correct_rate(batch)

    Note: `choices` is stored as a JSON list of {"key": "A", "text": "..."}.
    `correct_choice_key` is added (not explicitly in the spec table) so the
    API can grade answers without leaking the correct choice in the JSON
    payload sent to the client before answering.
    """

    class ExamType(models.TextChoices):
        CBT = "CBT", "CBT"
        KOKUSHI = "KOKUSHI", "医師国家試験"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "公開（全ユーザー）"
        UNIVERSITY_ONLY = "university_only", "学内限定"

    class Difficulty(models.IntegerChoices):
        EASY = 1, "易"
        NORMAL = 2, "標準"
        HARD = 3, "難"

    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "M", "多選択肢択一"
        SEQUENTIAL = "Q", "順次解答四連問"

    class Status(models.TextChoices):
        DRAFT = "draft", "下書き"
        PENDING = "pending", "審査待ち"
        PUBLISHED = "published", "公開"
        REJECTED = "rejected", "却下"

    class Source(models.TextChoices):
        OFFICIAL = "official", "公式"
        LLM = "llm", "LLM生成"
        USER = "user", "ユーザー作成"

    category = models.CharField(max_length=100)
    topic = models.CharField(
        max_length=100,
        blank=True,
        help_text="カテゴリ内のサブトピック（疾患名など、任意）",
    )
    difficulty = models.IntegerField(
        choices=Difficulty.choices, default=Difficulty.NORMAL
    )
    exam_type = models.CharField(max_length=10, choices=ExamType.choices)
    question_text = models.TextField(
        blank=True, help_text="設問文（症例文など）"
    )
    choices = models.JSONField(
        help_text='[{"key": "A", "text": "..."}, ...]'
    )
    correct_choice_key = models.CharField(max_length=4)
    explanation = models.TextField()
    creator = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_questions",
        help_text="nullの場合は公式問題",
    )
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    university = models.ForeignKey(
        "accounts.University",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
        help_text="visibility=university_onlyの場合の閲覧範囲",
    )
    correct_rate = models.FloatField(
        default=0.0, help_text="バッチ集計される全体正答率"
    )
    answer_count = models.PositiveIntegerField(
        default=0, help_text="correct_rate の分母（解答時にインクリメント）"
    )
    question_type = models.CharField(
        max_length=1, choices=QuestionType.choices, default=QuestionType.MULTIPLE_CHOICE
    )
    blueprint_code = models.CharField(
        max_length=32, blank=True, db_index=True, help_text='例 "D-5-4)-(2)-③"'
    )
    class_group = models.CharField(
        max_length=2, blank=True, choices=[("I", "Ⅰ群"), ("II", "Ⅱ群")]
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.OFFICIAL
    )
    question_set = models.ForeignKey(
        QuestionSet,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="questions",
    )
    set_order = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="タイプQ内の1〜4"
    )
    reviewed_by = models.ForeignKey(
        "accounts.Profile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_questions",
        help_text="医学的正確性レビュー者",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = QuestionQuerySet.as_manager()

    # correct_rate は解答数がこの値に達するまで API では null を返す
    # （少数解答での誤解を避ける, spec 2.1）
    MIN_ANSWERS_FOR_CORRECT_RATE = 10

    class Meta:
        verbose_name = "問題"
        verbose_name_plural = "問題"
        indexes = [
            models.Index(fields=["status", "visibility", "category"]),
        ]

    def __str__(self):
        return f"[{self.category}] {self.id}"

    @property
    def public_correct_rate(self):
        if self.answer_count >= self.MIN_ANSWERS_FOR_CORRECT_RATE:
            return self.correct_rate
        return None


class QuestionReport(models.Model):
    """問題の通報（ユーザー作成問題の品質担保, spec 2.2）。同一問題に
    3件以上付くと自動で pending に戻し出題から外す (spec フェーズ7)."""

    AUTO_UNPUBLISH_THRESHOLD = 3

    class Reason(models.TextChoices):
        WRONG_ANSWER = "wrong_answer", "正解が誤っている"
        AMBIGUOUS = "ambiguous", "設問が曖昧"
        TYPO = "typo", "誤字脱字"
        INAPPROPRIATE = "inappropriate", "不適切な内容"
        OTHER = "other", "その他"

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="reports"
    )
    reporter = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="question_reports"
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "問題通報"
        verbose_name_plural = "問題通報"
        # 同一ユーザーの重複通報を防ぐ（3件閾値を実質3人にする）
        unique_together = ("question", "reporter")

    def __str__(self):
        return f"Q{self.question_id} - {self.reason}"


class AnswerHistory(models.Model):
    """spec: AnswerHistory: id, user_id, question_id, mastery_level, correct,
    answered_at, response_time_ms"""

    class MasteryLevel(models.TextChoices):
        DOUBLE_CIRCLE = "double_circle", "◎"
        CIRCLE = "circle", "○"
        TRIANGLE = "triangle", "△"
        CROSS = "cross", "✕"
        UNSTUDIED = "unstudied", "未演習"

    user = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="answer_histories"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="answer_histories"
    )
    mastery_level = models.CharField(
        max_length=20,
        choices=MasteryLevel.choices,
        default=MasteryLevel.UNSTUDIED,
    )
    correct = models.BooleanField()
    answered_at = models.DateTimeField(auto_now_add=True)
    response_time_ms = models.IntegerField()

    class Meta:
        verbose_name = "解答履歴"
        verbose_name_plural = "解答履歴"
        indexes = [
            models.Index(fields=["user", "question"]),
            # ランキング集計の期間フィルタ用 (spec §6)
            models.Index(fields=["user", "answered_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} - Q{self.question_id} - {'○' if self.correct else '✕'}"


class ReviewSchedule(models.Model):
    """spec: ReviewSchedule: user_id, question_id, next_review_at,
    interval_days, ease_factor（SM-2アルゴリズムベース）"""

    user = models.ForeignKey(
        "accounts.Profile", on_delete=models.CASCADE, related_name="review_schedules"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="review_schedules"
    )
    next_review_at = models.DateTimeField()
    interval_days = models.FloatField(default=1)
    ease_factor = models.FloatField(default=2.5)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "復習スケジュール"
        verbose_name_plural = "復習スケジュール"
        unique_together = ("user", "question")

    def __str__(self):
        return f"{self.user_id} - Q{self.question_id} - next:{self.next_review_at:%Y-%m-%d}"
