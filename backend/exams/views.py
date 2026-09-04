"""Ranking API (spec フェーズ3) + Mock-exam API (spec フェーズ5) + internal hook."""


from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from io import StringIO
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from config.internal_auth import require_internal_caller
from accounts.ranktier import (
    compute_tier,
    progress_for_points,
    rank_state,
    tier_for_top_fraction,
)
from exams.constants import MIN_QUESTIONS_FOR_ACCURACY_RANKING
from exams.ranking_utils import grade_ranked_rows
from exams.grading import apply_irt_score, grade_single_result
from exams.models import MockAnswer, MockExam, MockResult, RankingSnapshot
from quiz.serializers import QuestionSerializer

DISPLAY_NAME_FALLBACK = "匿名ユーザー"
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def current_period():
    return timezone.localtime().strftime("%Y-%m")


class RankingView(APIView):
    """GET /api/ranking/?scope=national|university|university_aggregate
                        &metric=solved|accuracy&period=all|YYYY-MM&limit=50

    レスポンスは entries に加えて自分の順位 (me) を必ず含める (spec 3-3)。
    メールアドレスは絶対に返さない。表示名未設定は「匿名ユーザー」。

    個人ランキング（national/university）は同学年の中での順位にする
    （対戦ランクは逆に全学年まとめる。学年ごとに解いている範囲が違う
    問題演習だけの特別扱い）。RankingSnapshot.rank は学年をまたいだ全体
    順位なので、ここでは使わず ranking_utils.grade_ranked_rows で
    学年ごとに順位を振り直す。university_aggregate（大学を1単位とする
    集計）は個人の学年に関係ないので対象外。
    """

    def get(self, request):
        scope = request.query_params.get("scope", RankingSnapshot.Scope.NATIONAL)
        metric = request.query_params.get("metric", RankingSnapshot.Metric.SOLVED)
        period = request.query_params.get("period", "all")
        try:
            limit = min(int(request.query_params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        except ValueError:
            raise exceptions.ValidationError("limit は整数で指定してください") from None

        if scope not in RankingSnapshot.Scope.values:
            raise exceptions.ValidationError("scope が不正です")
        if metric not in RankingSnapshot.Metric.values:
            raise exceptions.ValidationError("metric が不正です")

        profile = request.user
        qs = RankingSnapshot.objects.filter(scope=scope, period=period, metric=metric)

        if scope == RankingSnapshot.Scope.UNIVERSITY:
            if not profile.university_id:
                return Response(
                    {
                        "entries": [],
                        "me": {
                            "rank": None,
                            "value": None,
                            "eligible": False,
                            "reason": "学内ランキングには所属大学の設定が必要です。",
                        },
                        "computed_at": None,
                    }
                )
            qs = qs.filter(university_id=profile.university_id)

        if scope == RankingSnapshot.Scope.UNIVERSITY_AGGREGATE:
            entries_qs = qs.select_related("university_target").order_by("rank", "-value")[:limit]
            entries = [
                {
                    "rank": row.rank,
                    "university": row.university_target.name if row.university_target else None,
                    "value": row.value,
                    "sample_size": row.sample_size,
                    "is_me": bool(
                        profile.university_id
                        and row.university_target_id == profile.university_id
                    ),
                }
                for row in entries_qs
            ]
            me = self._build_me_aggregate(profile, qs)
            computed_at = qs.values_list("computed_at", flat=True).first()
            return Response({"entries": entries, "me": me, "computed_at": computed_at})

        computed_at = qs.values_list("computed_at", flat=True).first()
        if profile.grade is None:
            return Response(
                {
                    "entries": [],
                    "me": {
                        "rank": None,
                        "value": None,
                        "eligible": False,
                        "reason": "学年が未設定です。マイページから設定してください。",
                        "total": 0,
                    },
                    "computed_at": computed_at,
                }
            )

        ranked_rows = grade_ranked_rows(
            qs.select_related("profile", "profile__university"), profile.grade
        )
        entries = [
            {
                "rank": rank,
                "display_name": (
                    (row.profile.display_name or DISPLAY_NAME_FALLBACK)
                    if row.profile
                    else DISPLAY_NAME_FALLBACK
                ),
                "university": (
                    row.profile.university.name
                    if row.profile and row.profile.university
                    else None
                ),
                "value": row.value,
                "is_me": row.profile_id == profile.id,
            }
            for rank, row in ranked_rows[:limit]
        ]
        me = self._build_me_individual(profile, scope, metric, period, ranked_rows)
        return Response({"entries": entries, "me": me, "computed_at": computed_at})

    def _build_me_aggregate(self, profile, qs):
        total = qs.count()
        if not profile.university_id:
            return {
                "rank": None,
                "value": None,
                "eligible": False,
                "reason": "所属大学が未設定です。",
                "total": total,
            }
        row = qs.filter(university_target_id=profile.university_id).first()
        if row:
            return {
                "rank": row.rank,
                "value": row.value,
                "eligible": True,
                "reason": None,
                "total": total,
            }
        return {
            "rank": None,
            "value": None,
            "eligible": False,
            "reason": "対象メンバーが5人未満のため、大学ランキングの対象外です。",
            "total": total,
        }

    def _build_me_individual(self, profile, scope, metric, period, ranked_rows):
        # total: 同学年内の母集団サイズ。フロントの「上位X%」表示に使う。
        total = len(ranked_rows)
        match = next(
            ((rank, row) for rank, row in ranked_rows if row.profile_id == profile.id), None
        )
        if match:
            rank, row = match
            return {
                "rank": rank,
                "value": row.value,
                "eligible": True,
                "reason": None,
                "total": total,
            }

        if metric == RankingSnapshot.Metric.ACCURACY:
            solved_row = RankingSnapshot.objects.filter(
                scope=scope,
                period=period,
                metric=RankingSnapshot.Metric.SOLVED,
                profile=profile,
            )
            if scope == RankingSnapshot.Scope.UNIVERSITY:
                solved_row = solved_row.filter(university_id=profile.university_id)
            solved = int(solved_row.values_list("value", flat=True).first() or 0)
            if solved < MIN_QUESTIONS_FOR_ACCURACY_RANKING:
                return {
                    "rank": None,
                    "value": None,
                    "eligible": False,
                    "reason": (
                        f"正答率ランキングは{MIN_QUESTIONS_FOR_ACCURACY_RANKING}問以上の解答が"
                        f"必要です（現在 {solved}問）"
                    ),
                    "total": total,
                }

        return {"rank": None, "value": None, "eligible": True, "reason": None, "total": total}


class ExamRankingHistoryView(APIView):
    """GET /api/ranking/exams/ — 自分の模試順位の履歴 (spec 3-3)。"""

    def get(self, request):
        results = (
            MockResult.objects.filter(user=request.user)
            .select_related("mock_exam")
            .order_by("-mock_exam__start_at")
        )
        return Response(
            [
                {
                    "mock_exam_id": r.mock_exam_id,
                    "title": r.mock_exam.title,
                    "kind": r.mock_exam.kind,
                    "exam_type": r.mock_exam.exam_type,
                    "start_at": r.mock_exam.start_at,
                    "score": r.score,
                    "rank": r.rank,
                    "university_rank": r.university_rank,
                    "deviation_score": r.deviation_score,
                    "points_delta": r.points_delta,
                    "irt_scaled_score": r.irt_scaled_score,
                    "submitted": r.submitted_at is not None,
                }
                for r in results
                if r.submitted_at is not None or r.mock_exam.kind != MockExam.Kind.CBT_ONCE
            ]
        )


class PointsRankingView(APIView):
    """GET /api/ranking/points/?scope=national|university&limit=50 —
    対戦＋模試（週次/月次）合算ポイントのランキングとランク階層
    （SS/S/A/B/C/D, spec: 上位5/25/40/60/80/100%）。

    scope=university は「同じ大学内での順位」に絞るが、各人のランク階層
    バッチはあくまで全国母集団での位置（tier はランキング画面の他の指標と
    同様、常に全国基準）。対象は ranked_matches>=1 のユーザーのみ
    （一度もランク付き対戦・模試をしていないユーザーは母集団にも含めない）。
    AI対戦相手のプロフィールは除外。
    """

    def get(self, request):
        try:
            limit = min(int(request.query_params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        except ValueError:
            raise exceptions.ValidationError("limit は整数で指定してください") from None
        scope = request.query_params.get("scope", "national")
        if scope not in ("national", "university"):
            raise exceptions.ValidationError("scope が不正です")

        national_qs = Profile.objects.filter(is_ai=False, ranked_matches__gte=1)
        total = national_qs.count()

        def tier_of(p):
            strictly_better = national_qs.filter(points__gt=p.points).count()
            return tier_for_top_fraction(strictly_better / total) if total else None

        if scope == "university":
            if not request.user.university_id:
                return Response(
                    {
                        "entries": [],
                        "me": {
                            "points": request.user.points,
                            "tier": None,
                            "ranked_matches": request.user.ranked_matches,
                            "eligible": False,
                            "reason": "学内ランキングには所属大学の設定が必要です。",
                        },
                        "total_ranked": total,
                    }
                )
            listing_qs = national_qs.filter(university_id=request.user.university_id)
        else:
            listing_qs = national_qs

        listing_qs = listing_qs.select_related("university")
        ordered = listing_qs.order_by("-points", "id")[:limit]
        entries = [
            {
                "rank": i,
                "display_name": p.display_name or DISPLAY_NAME_FALLBACK,
                "university": p.university.name if p.university else None,
                "points": p.points,
                "tier": tier_of(p),
                "progress": progress_for_points(p.points),
                "is_me": p.id == request.user.id,
            }
            for i, p in enumerate(ordered, start=1)
        ]

        my_state = rank_state(request.user)
        return Response(
            {
                "entries": entries,
                "me": {
                    "points": request.user.points,
                    "tier": my_state["tier"],
                    # ランク内の進捗%（100を超えると次のランクへ上がって0%に戻る）
                    "progress": my_state["progress"],
                    "next_tier": my_state["next_tier"],
                    "ranked_matches": request.user.ranked_matches,
                    "eligible": my_state["tier"] is not None,
                },
                "total_ranked": total,
            }
        )


# --------------------------------------------------------------------------
# Mock exams (spec フェーズ5)
# --------------------------------------------------------------------------


def exam_status_for(exam, result, now=None):
    """CBT模試（生涯1回）は受験者ごとに完了タイミングが違うため、この模試
    インスタンス全体の状態ではなく個人の提出有無で見かけ上のステータスを返す。"""
    if exam.kind == MockExam.Kind.CBT_ONCE:
        if result and result.submitted_at:
            return MockExam.Status.GRADED
        return MockExam.Status.OPEN
    return exam.effective_status(now)


def exam_payload(exam, result=None, now=None):
    data = {
        "id": exam.id,
        "title": exam.title,
        "kind": exam.kind,
        "exam_type": exam.exam_type,
        "start_at": exam.start_at,
        "end_at": exam.end_at,
        "status": exam_status_for(exam, result, now),
        "question_count": exam.question_count,
        "duration_minutes": exam.duration_minutes,
        "target_grade_min": exam.target_grade_min,
        "target_grade_max": exam.target_grade_max,
        "my_result": None,
    }
    if result:
        data["my_result"] = {
            "started_at": result.started_at,
            "submitted_at": result.submitted_at,
            "deadline": result.deadline() if result.started_at else None,
        }
    return data


def ensure_exams_exist(now=None):
    """受験できる模試が1件も無ければ、その場で定期開催分を作る。

    模試の生成は Vercel Cron（/api/internal/create-exams/）に任せているが、
    Cron が未設定・失敗している環境や、デプロイ直後でまだ一度も走っていない
    環境では模試が1件も無く、一覧が「受験できる模試はありません」だけに
    なってしまう。一覧を開いたときに埋め合わせておく。

    create_scheduled_exam は冪等（同じ日付・未終了インスタンスがあれば
    作らない）で、月次は今月分が無ければ即開催で作る。開催中の模試が
    できた時点でこの関数は何もしなくなるので、毎回の一覧表示で走ることは
    ない。問題プールが足りなくても仮設問で埋まるので失敗しない。
    """
    now = now or timezone.now()
    if MockExam.objects.filter(start_at__lte=now, end_at__gte=now).exists():
        return
    for kind in (MockExam.Kind.MONTHLY, MockExam.Kind.LARGE, MockExam.Kind.CBT_ONCE):
        try:
            call_command("create_scheduled_exam", "--kind", kind, stdout=StringIO())
        except CommandError:
            # 1つの kind が作れなくても、他の kind の生成と一覧表示は続ける。
            continue


class ExamListView(APIView):
    """GET /api/exams/ — status・対象学年でフィルタ (spec フェーズ5)."""

    def get(self, request):
        now = timezone.now()
        ensure_exams_exist(now)
        qs = MockExam.objects.order_by("-start_at")
        status_filter = request.query_params.get("status")
        grade = request.user.grade
        my_results = {
            r.mock_exam_id: r for r in MockResult.objects.filter(user=request.user)
        }
        rows = []
        for exam in qs:
            if grade is not None:
                if exam.target_grade_min and grade < exam.target_grade_min:
                    continue
                if exam.target_grade_max and grade > exam.target_grade_max:
                    continue
            payload = exam_payload(exam, my_results.get(exam.id), now)
            if status_filter and payload["status"] != status_filter:
                continue
            rows.append(payload)
        return Response(rows)


class ExamStartView(APIView):
    """POST /api/exams/{id}/start/ — MockResult 作成。二重受験不可 (spec フェーズ5)。

    CBT模試（kind=cbt_once）は「いつでも受験できるが生涯1回だけ」なので、
    この模試インスタンスに限らず kind=cbt_once の受験歴があれば拒否する。
    """

    def post(self, request, exam_id):
        exam = get_object_or_404(MockExam, pk=exam_id)
        if not exam.is_open_for(request.user.grade):
            raise exceptions.ValidationError("この模試は現在受験できません。")
        if exam.kind == MockExam.Kind.CBT_ONCE:
            if MockResult.objects.filter(
                user=request.user, mock_exam__kind=MockExam.Kind.CBT_ONCE
            ).exists():
                raise exceptions.ValidationError(
                    "CBT模試はすでに受験済みです（生涯1回のみ受験できます）。"
                )
        elif MockResult.objects.filter(user=request.user, mock_exam=exam).exists():
            raise exceptions.ValidationError("すでに受験を開始しています（二重受験不可）。")
        result = MockResult.objects.create(
            user=request.user, mock_exam=exam, started_at=timezone.now()
        )
        return Response(exam_payload(exam, result), status=201)


def get_my_open_result(request, exam_id):
    exam = get_object_or_404(MockExam, pk=exam_id)
    result = MockResult.objects.filter(user=request.user, mock_exam=exam).first()
    if result is None or result.started_at is None:
        raise exceptions.ValidationError("受験を開始していません。")
    return exam, result


class ExamQuestionsView(APIView):
    """GET /api/exams/{id}/questions/ — MockQuestion 順。正解・解説は返さない
    （QuestionSerializer が除外を担保, spec 6 セキュリティ）。"""

    def get(self, request, exam_id):
        exam, result = get_my_open_result(request, exam_id)
        questions = [
            mq.question
            for mq in exam.mock_questions.select_related(
                "question", "question__question_set"
            ).order_by("order")
        ]
        answers = {
            a.question_id: a.selected_choice_key for a in result.answers.all()
        }
        return Response(
            {
                "deadline": result.deadline(),
                "submitted_at": result.submitted_at,
                "kind": exam.kind,
                "questions": QuestionSerializer(questions, many=True).data,
                "my_answers": answers,
            }
        )


class ExamAnswerView(APIView):
    """POST /api/exams/{id}/answers/ — MockAnswer を upsert（採点結果は返さ
    ない）。時間超過後・提出後は拒否 (spec フェーズ5)."""

    def post(self, request, exam_id):
        exam, result = get_my_open_result(request, exam_id)
        if result.submitted_at is not None:
            raise exceptions.ValidationError("提出済みのため変更できません。")
        if timezone.now() > result.deadline():
            raise exceptions.ValidationError("制限時間を超過しています。")

        question_id = request.data.get("question_id")
        selected = request.data.get("selected_choice_key", "")
        if not question_id:
            raise exceptions.ValidationError("question_id は必須です。")
        if not exam.mock_questions.filter(question_id=question_id).exists():
            raise exceptions.ValidationError("この模試の設問ではありません。")

        MockAnswer.objects.update_or_create(
            mock_result=result,
            question_id=question_id,
            defaults={
                "selected_choice_key": selected,
                "response_time_ms": int(request.data.get("response_time_ms", 0) or 0),
            },
        )
        return Response({"saved": True, "answered": result.answers.count()})


class ExamSubmitView(APIView):
    """POST /api/exams/{id}/submit/ — submitted_at 記録。以後変更不可。

    CBT模試（生涯1回）は受験者ごとに終了タイミングが違い、他の受験者の
    終了を待つ共有の締切がないため、提出と同時にこの1件だけを個別採点する
    （通常の週次/月次/大型模試は grade_mock_exam のバッチ採点を待つ）。
    """

    def post(self, request, exam_id):
        exam, result = get_my_open_result(request, exam_id)
        if result.submitted_at is None:
            result.submitted_at = timezone.now()
            result.save(update_fields=["submitted_at"])
            if exam.kind == MockExam.Kind.CBT_ONCE:
                self._grade_cbt_once(exam, result)
        return Response({"submitted_at": result.submitted_at})

    def _grade_cbt_once(self, exam, result):
        correct_questions = {
            mq.question_id: mq.question
            for mq in exam.mock_questions.select_related("question")
        }
        grade_single_result(result, correct_questions)
        apply_irt_score(result, correct_questions)

        # 参考値としての順位/偏差値: これまでにこの模試を終えた受験者との
        # 比較（全体の締切を待たず、この受験者1件だけを確定させる簡易版）。
        prior = list(
            MockResult.objects.filter(
                mock_exam__kind=MockExam.Kind.CBT_ONCE, submitted_at__isnull=False
            ).exclude(pk=result.pk)
        )
        cohort = prior + [result]
        scores = [r.score for r in cohort]
        n = len(scores)
        below = sum(1 for s in scores if s < result.score)
        result.percentile = round(below / n * 100, 1) if n else None
        result.rank = sum(1 for s in scores if s > result.score) + 1
        import statistics as _stats

        stdev = _stats.pstdev(scores) if n > 1 else 0
        mean = _stats.fmean(scores) if n else result.score
        result.deviation_score = round(50 + 10 * (result.score - mean) / stdev, 1) if stdev else 50.0

        result.save(
            update_fields=[
                "score", "section_scores", "irt_theta", "irt_scaled_score",
                "percentile", "rank", "deviation_score",
            ]
        )


def next_month_first_local(after):
    """``after`` の翌月1日 0:00（JST）。模試の成績がランキングに出る日。

    集計は開催が終わってから走るので、結果画面では「翌月1日にランキング
    タブで見られる」と案内する。
    """
    local = timezone.localtime(after)
    year, month = local.year, local.month + 1
    if month == 13:
        month, year = 1, year + 1
    return local.replace(
        year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def build_review(exam, result):
    """模試の全問見直し。設問・選択肢・自分の解答・正解・解説を返す。

    問題演習の画面にそのまま渡せるよう、QuestionSerializer と同じ形の
    設問データ（choices・category・difficulty など）も含める。
    """
    mine = {a.question_id: a.selected_choice_key for a in result.answers.all()}
    rows = []
    for mq in (
        exam.mock_questions.select_related("question", "question__question_set")
        .order_by("order")
    ):
        question = mq.question
        my_choice = mine.get(mq.question_id, "")
        rows.append(
            {
                "order": mq.order,
                "question_id": question.id,
                "category": question.category,
                "exam_type": question.exam_type,
                "difficulty": question.difficulty,
                "question_type": question.question_type,
                "set_order": mq.order,
                "case_stem": (
                    question.question_set.case_stem if question.question_set_id else None
                ),
                "question_text": question.question_text,
                "choices": question.choices,
                "correct_choice_key": question.correct_choice_key,
                "explanation": question.explanation,
                "my_choice": my_choice,
                "answered": bool(my_choice),
                "correct": my_choice == question.correct_choice_key,
            }
        )
    return rows


class ExamResultView(APIView):
    """GET /api/exams/{id}/result/ — status=graded になるまで「採点中」。"""

    def get(self, request, exam_id):
        exam = get_object_or_404(MockExam, pk=exam_id)
        result = MockResult.objects.filter(user=request.user, mock_exam=exam).first()
        graded = exam_status_for(exam, result) == MockExam.Status.GRADED
        if result is None or result.submitted_at is None:
            # まだ提出していない（＝受験記録が無いか受験途中）。
            return Response({"status": "grading", "message": "採点中です。しばらくお待ちください。"})

        review = build_review(exam, result)
        # 得点・正誤・解説は提出した時点で本人に返す。順位や偏差値と違って
        # 他の受験者の結果を待つ必要がなく、待たせるほど復習から遠ざかる。
        # result.score は採点コマンドが入れる値で、未採点なら 0 のままなので、
        # 採点前は見直しから数え直す（0点と「まだ集計していない」は別物）。
        my_score = result.score if graded else sum(1 for row in review if row["correct"])
        common = {
            "title": exam.title,
            "kind": exam.kind,
            "exam_type": exam.exam_type,
            "score": my_score,
            "max_score": exam.mock_questions.count(),
            "review": review,
            # 全国順位・偏差値は集計後にランキングタブへ出る。
            "ranking_available_at": next_month_first_local(exam.end_at),
        }
        if not graded:
            return Response({**common, "status": "submitted"})

        total = MockResult.objects.filter(mock_exam=exam).count()
        return Response(
            {
                **common,
                "status": "graded",
                "rank": result.rank,
                "out_of": total,
                "university_rank": result.university_rank,
                "percentile": result.percentile,
                "deviation_score": result.deviation_score,
                "section_scores": result.section_scores,
                "section_deviation_scores": result.section_deviation_scores,
                "score_distribution": result.score_distribution or None,
                "points_delta": result.points_delta,
                "points_after": request.user.points if result.points_delta is not None else None,
                "tier_after": compute_tier(request.user) if result.points_delta is not None else None,
                "irt_theta": result.irt_theta,
                "irt_scaled_score": result.irt_scaled_score,
            }
        )


class InternalAggregateView(APIView):
    """POST/GET /api/internal/aggregate/ — ランキング集計のトリガ (spec 3-3)。

    pg_cron → Edge Function（POST + X-Internal-Token）と、Vercel Cron
    （GET + Authorization: Bearer CRON_SECRET）の両方から叩ける。
    JWT 認証は使わない。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """Vercel Cron は GET しか送れないので、POST と同じ処理を用意する。"""
        return self.post(request)

    def post(self, request):
        require_internal_caller(request)

        periods = (request.data or {}).get("periods") or ["all", current_period()]
        for period in periods:
            call_command("aggregate_rankings", "--period", period)
        return Response({"status": "ok", "periods": periods})


class InternalCreateExamsView(APIView):
    """POST/GET /api/internal/create-exams/ — 定期開催模試の自動生成トリガ。

    毎日1回 Vercel Cron から叩く想定。create_scheduled_exam は kind ごとに
    「同じ日付の分は作成済みならスキップ」（monthly/large）・「未終了の
    インスタンスがあれば作成しない」（cbt_once）という冪等性を持つので、
    このエンドポイント自体は毎日何度呼ばれても安全（多くの日は何も
    作成せず終わる）。"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return self.post(request)

    def post(self, request):
        require_internal_caller(request)

        # kind ごとに独立させる: 1つの exam_type で問題プールが尽きていても
        # （CommandError）他の kind の生成まで巻き込んで失敗させない。
        created = {}
        for kind in (
            MockExam.Kind.MONTHLY,
            MockExam.Kind.LARGE,
            MockExam.Kind.CBT_ONCE,
        ):
            out = StringIO()
            try:
                call_command("create_scheduled_exam", "--kind", kind, stdout=out)
                created[kind] = out.getvalue().strip()
            except CommandError as e:
                created[kind] = f"error: {e}"
        return Response({"status": "ok", "created": created})
