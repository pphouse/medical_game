"""管理画面のAPI (/api/admin/...)。

学習者向けAPIとは分けてある。学習者向けは「公開済みだけ」を前提に組んで
おり (Question.objects.visible_to)、管理側はそこを外して全 status を扱う
必要があるため、同じビューに混ぜると公開ゲートを踏み外しやすい。

権限は既定で IsModerator（moderator と admin）。ロール変更だけは
権限昇格になるので IsAdmin に絞る。
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from config.permissions import IsAdmin, IsModerator

from .admin_serializers import AdminQuestionSerializer, AdminReportSerializer
from .categories import CATEGORIES_BY_EXAM
from .models import Question, QuestionReport

# 一括操作で一度に触れる上限。UIの取り違えで全問題を書き換える事故を防ぐ。
BULK_MAX = 2000


class AdminPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _filtered_questions(params):
    """一覧・一括操作で共通の絞り込み。

    同じ絞り込みを一覧と一括操作の両方で使うことで、画面に出ている集合と
    一括操作の対象が食い違わないようにする。
    """
    qs = Question.objects.all()
    status = params.get("status")
    exam_type = params.get("exam_type")
    category = params.get("category")
    source = params.get("source")
    keyword = params.get("q")
    if status:
        qs = qs.filter(status=status)
    if exam_type:
        qs = qs.filter(exam_type=exam_type)
    if category:
        qs = qs.filter(category=category)
    if source:
        qs = qs.filter(source=source)
    if keyword:
        qs = qs.filter(
            Q(question_text__icontains=keyword)
            | Q(explanation__icontains=keyword)
            | Q(topic__icontains=keyword)
            | Q(category__icontains=keyword)
        )
    return qs


class AdminStatsView(APIView):
    """ダッシュボードの数字。status / exam_type / source 別の内訳。"""

    permission_classes = [IsModerator]

    def get(self, request):
        def tally(field):
            return {
                row[field]: row["n"]
                for row in Question.objects.values(field).annotate(n=Count("id"))
            }

        categories = (
            Question.objects.values("category", "exam_type")
            .annotate(n=Count("id"))
            .order_by("-n")[:50]
        )
        return Response(
            {
                "total": Question.objects.count(),
                "by_status": tally("status"),
                "by_exam_type": tally("exam_type"),
                "by_source": tally("source"),
                "categories": [
                    {"category": c["category"], "exam_type": c["exam_type"], "total": c["n"]}
                    for c in categories
                ],
                "open_reports": QuestionReport.objects.count(),
                "users": Profile.objects.count(),
                # 画面の分野プルダウン用。自由入力だと「循環器」と「循環器系」の
                # ように同じ分野が別名で増えるので、選ばせる。
                # 科目立ては CBT と国試で違うので、試験種別ごとに返す。
                "canonical_categories": {
                    exam: list(names) for exam, names in CATEGORIES_BY_EXAM.items()
                },
            }
        )


class AdminQuestionListView(APIView):
    """全問題の一覧（status を問わない）と新規作成。"""

    permission_classes = [IsModerator]

    def get(self, request):
        qs = (
            _filtered_questions(request.query_params)
            .annotate(annotated_report_count=Count("reports"))
            .select_related("question_set")
            .order_by("-created_at", "-id")
        )
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            AdminQuestionSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = AdminQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 管理者が直接書いた問題は「公式」扱い。LLM生成と混ぜると
        # レビュー状況の集計が読めなくなる。
        question = serializer.save(
            source=Question.Source.OFFICIAL,
            creator=request.user,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        return Response(AdminQuestionSerializer(question).data, status=201)


class AdminQuestionDetailView(APIView):
    """1問の取得・編集・削除。

    学習者向けの QuestionDetailView は解答履歴のある問題の本文編集を
    禁止しているが、こちらは誤りの訂正が目的なので許可する。ただし
    履歴のある問題を書き換えると過去の正誤が意味を失うため、
    answer_count を返して画面側で警告を出せるようにしている。
    """

    permission_classes = [IsModerator]

    def get(self, request, question_id):
        question = get_object_or_404(Question, pk=question_id)
        return Response(AdminQuestionSerializer(question).data)

    def patch(self, request, question_id):
        question = get_object_or_404(Question, pk=question_id)
        serializer = AdminQuestionSerializer(question, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "status" in request.data:
            serializer.save(reviewed_by=request.user, reviewed_at=timezone.now())
        else:
            serializer.save()
        return Response(AdminQuestionSerializer(question).data)

    def delete(self, request, question_id):
        question = get_object_or_404(Question, pk=question_id)
        question.delete()
        return Response(status=204)


class AdminBulkStatusView(APIView):
    """まとめて status を変える。

    対象は ids で明示するか、一覧と同じ絞り込み + expected_count で指定する。
    expected_count を必須にしているのは、画面に出ている件数と実際の対象が
    ずれたまま実行される事故を防ぐため（絞り込みの取り違えで全問題を
    公開してしまう類）。
    """

    permission_classes = [IsModerator]

    def post(self, request):
        new_status = request.data.get("status")
        valid = [s for s, _ in Question.Status.choices]
        if new_status not in valid:
            raise exceptions.ValidationError({"status": f"status は {valid} のいずれか"})

        ids = request.data.get("ids")
        if ids is not None:
            if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
                raise exceptions.ValidationError({"ids": "整数の配列で指定してください。"})
            if len(ids) > BULK_MAX:
                raise exceptions.ValidationError(
                    {"ids": f"一度に変更できるのは{BULK_MAX}件までです。"}
                )
            qs = Question.objects.filter(pk__in=ids)
        else:
            filters = request.data.get("filters")
            expected = request.data.get("expected_count")
            if not isinstance(filters, dict) or not isinstance(expected, int):
                raise exceptions.ValidationError(
                    "ids、または filters と expected_count の組で指定してください。"
                )
            qs = _filtered_questions(filters)
            actual = qs.count()
            if actual != expected:
                raise exceptions.ValidationError(
                    {
                        "expected_count": (
                            f"対象件数が変わっています（画面: {expected}件 / 現在: {actual}件）。"
                            "一覧を読み込み直してからやり直してください。"
                        )
                    }
                )
            if actual > BULK_MAX:
                raise exceptions.ValidationError(
                    {"filters": f"一度に変更できるのは{BULK_MAX}件までです。"}
                )

        updated = qs.update(
            status=new_status, reviewed_by=request.user, reviewed_at=timezone.now()
        )
        return Response({"updated": updated, "status": new_status})


class AdminReportListView(APIView):
    """通報の一覧。多い順に問題をまとめて出す。"""

    permission_classes = [IsModerator]

    def get(self, request):
        qs = QuestionReport.objects.select_related("question").order_by("-created_at")
        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(AdminReportSerializer(page, many=True).data)


class AdminUserListView(APIView):
    """利用者一覧とロール変更。

    ロール変更は権限昇格そのものなので admin 限定（IsAdmin）。
    moderator が自分や他人を admin にできてしまうと権限分離の意味がない。
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        rows = (
            Profile.objects.select_related("university")
            .order_by("-role", "display_name")[:500]
        )
        return Response(
            [
                {
                    "id": str(p.id),
                    "display_name": p.display_name or "",
                    "role": p.role,
                    "grade": p.grade,
                    "student_verified": p.student_verified,
                    "university": p.university.name if p.university_id else None,
                }
                for p in rows
            ]
        )

    def patch(self, request):
        user_id = request.data.get("id")
        role = request.data.get("role")
        valid = [r for r, _ in Profile.Role.choices]
        if role not in valid:
            raise exceptions.ValidationError({"role": f"role は {valid} のいずれか"})
        profile = get_object_or_404(Profile, pk=user_id)
        if profile.id == request.user.id and role != Profile.Role.ADMIN:
            # 最後の管理者が自分を降格させると誰も管理できなくなる。
            raise exceptions.ValidationError(
                {"role": "自分自身の管理者権限は外せません。他の管理者に依頼してください。"}
            )
        profile.role = role
        profile.save(update_fields=["role"])
        return Response({"id": str(profile.id), "role": profile.role})
