"""復習の絞り込み演習。

科目・評価（◎○△✕未演習）・演習回数を掛け合わせて出題対象を作る。復習デッキ
（SM-2 の再出題タイミング）とは別物で、こちらは「自分で条件を決めて解き直す」
ための入口。

    GET /api/quiz/review-filter/?categories=循環器,呼吸器
                                &mastery=cross,triangle,unstudied
                                &attempts=1,2,3plus
                                &exam_type=CBT

いずれの絞り込みも省略時は「制限なし」。空文字で渡された場合も同じ扱いにする
（フロントで全解除したときに `categories=` が飛んでくる）。
"""

from django.db.models import Count
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AnswerHistory, Question
from .serializers import QuestionSerializer
from .views import latest_answers

# 演習回数のまとめ方。3回以上は個別に分けても選びにくいので一つにする。
ATTEMPT_BUCKETS = {"1": (1, 1), "2": (2, 2), "3plus": (3, None)}

MASTERY_VALUES = set(AnswerHistory.MasteryLevel.values)

# 一度に返す上限。条件次第で全問が該当しうるので、演習セットとして現実的な
# 大きさで頭打ちにする。
MAX_QUESTIONS = 500


def _csv_param(request, name):
    """カンマ区切りのクエリを集合で返す。未指定・空文字はどちらも None。"""
    raw = request.query_params.get(name)
    if raw is None:
        return None
    values = {v.strip() for v in raw.split(",") if v.strip()}
    return values or None


class ReviewFilterView(APIView):
    """条件に合う問題を返す。フロントはこれをそのまま演習セットにする。"""

    def get(self, request):
        visible = Question.objects.visible_to(request.user)

        exam_type = request.query_params.get("exam_type")
        if exam_type:
            visible = visible.filter(exam_type=exam_type)

        categories = _csv_param(request, "categories")
        if categories:
            visible = visible.filter(category__in=categories)

        mastery = _csv_param(request, "mastery")
        if mastery:
            unknown = mastery - MASTERY_VALUES
            if unknown:
                raise exceptions.ValidationError(
                    f"未知の評価です: {', '.join(sorted(unknown))}"
                )
            visible = self._filter_by_mastery(request.user, visible, mastery)

        attempts = _csv_param(request, "attempts")
        if attempts:
            unknown = attempts - set(ATTEMPT_BUCKETS)
            if unknown:
                raise exceptions.ValidationError(
                    f"未知の演習回数です: {', '.join(sorted(unknown))}"
                )
            visible = self._filter_by_attempts(request.user, visible, attempts)

        total = visible.count()
        page = visible.select_related("question_set").order_by("id")[:MAX_QUESTIONS]

        history_by_question = {
            row.question_id: row
            for row in latest_answers(request.user).filter(
                question_id__in=[q.id for q in page]
            )
        }
        serializer = QuestionSerializer(
            page, many=True, context={"history_by_question": history_by_question}
        )
        return Response(
            {"count": total, "truncated": total > MAX_QUESTIONS, "results": serializer.data}
        )

    def _filter_by_mastery(self, user, qs, mastery):
        """最新の解答の評価で絞る。

        「未演習」は一度も解いていない問題と、最後に未演習へ戻した問題の両方。
        他の評価と一緒に選べるよう、OR で足し合わせる。
        """
        latest = latest_answers(user)
        rated = mastery - {AnswerHistory.MasteryLevel.UNSTUDIED}

        matched_ids = set()
        if rated:
            matched_ids |= set(
                latest.filter(mastery_level__in=rated).values_list(
                    "question_id", flat=True
                )
            )

        if AnswerHistory.MasteryLevel.UNSTUDIED in mastery:
            studied = set(
                latest.exclude(
                    mastery_level=AnswerHistory.MasteryLevel.UNSTUDIED
                ).values_list("question_id", flat=True)
            )
            # 一度も解いていない問題は latest に行が無いので、除外側で表現する。
            return qs.filter(id__in=matched_ids) | qs.exclude(id__in=studied)

        return qs.filter(id__in=matched_ids)

    def _filter_by_attempts(self, user, qs, attempts):
        """解答回数で絞る。回数は同じ問題への解答行数を数える。"""
        counts = (
            AnswerHistory.objects.filter(user=user)
            .values("question_id")
            .annotate(n=Count("id"))
        )
        by_question = {row["question_id"]: row["n"] for row in counts}

        wanted = set()
        for bucket in attempts:
            low, high = ATTEMPT_BUCKETS[bucket]
            for question_id, n in by_question.items():
                if n >= low and (high is None or n <= high):
                    wanted.add(question_id)
        return qs.filter(id__in=wanted)
