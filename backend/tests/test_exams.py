import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import University
from accounts.ranktier import STARTING_POINTS
from exams.models import MockAnswer, MockExam, MockQuestion, MockResult
from quiz.models import AnswerHistory

from .helpers import auth_client, make_question

pytestmark = pytest.mark.django_db


def make_exam(n_questions=4, *, opens_in=-1, closes_in=60, duration=120, **kwargs):
    now = timezone.now()
    exam = MockExam.objects.create(
        title="テスト模試",
        start_at=now + datetime.timedelta(minutes=opens_in),
        end_at=now + datetime.timedelta(minutes=closes_in),
        question_count=n_questions,
        duration_minutes=duration,
        **kwargs,
    )
    for i in range(n_questions):
        question = make_question(
            question_text=f"模試設問{i}",
            correct_choice_key="A",
            blueprint_code="D-5-4)-(1)-①" if i % 2 == 0 else "D-7-4)-(3)-①",
        )
        MockQuestion.objects.create(mock_exam=exam, question=question, order=i + 1)
    return exam


def start_and_answer_all(client, exam, key="A"):
    client.post(f"/api/exams/{exam.id}/start/")
    questions = client.get(f"/api/exams/{exam.id}/questions/").json()["questions"]
    for q in questions:
        client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": q["id"], "selected_choice_key": key, "response_time_ms": 1000},
            format="json",
        )
    client.post(f"/api/exams/{exam.id}/submit/")


class TestExamFlow:
    def test_start_only_within_window(self):
        client, _ = auth_client()
        not_open = make_exam(opens_in=30)  # 30分後開始
        assert client.post(f"/api/exams/{not_open.id}/start/").status_code == 400
        closed = make_exam(opens_in=-120, closes_in=-30)
        assert client.post(f"/api/exams/{closed.id}/start/").status_code == 400

    def test_double_start_rejected(self):
        client, _ = auth_client()
        exam = make_exam()
        assert client.post(f"/api/exams/{exam.id}/start/").status_code == 201
        res = client.post(f"/api/exams/{exam.id}/start/")
        assert res.status_code == 400
        assert "二重受験" in res.content.decode()

    def test_grade_filter(self):
        client, _ = auth_client(grade=2)
        exam = make_exam(target_grade_min=4, target_grade_max=6)
        assert client.post(f"/api/exams/{exam.id}/start/").status_code == 400
        assert client.get("/api/exams/").json() == []

    def test_questions_hide_answers(self):
        client, _ = auth_client()
        exam = make_exam()
        client.post(f"/api/exams/{exam.id}/start/")
        body = client.get(f"/api/exams/{exam.id}/questions/").json()
        assert len(body["questions"]) == 4
        text = str(body)
        assert "correct_choice_key" not in text
        assert "explanation" not in text

    def test_questions_include_exam_kind_for_block_display(self):
        """CBT模試のブロック表示（フロント側）に使う。"""
        client, _ = auth_client(grade=4)
        exam = make_exam(kind=MockExam.Kind.CBT_ONCE, exam_type="CBT")
        client.post(f"/api/exams/{exam.id}/start/")
        body = client.get(f"/api/exams/{exam.id}/questions/").json()
        assert body["kind"] == "cbt_once"

    def test_answers_rejected_after_time_limit(self):
        client, profile = auth_client()
        exam = make_exam(duration=1, closes_in=600)
        client.post(f"/api/exams/{exam.id}/start/")
        question_id = exam.mock_questions.first().question_id

        # 制限時間内は保存できる
        ok = client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "A"},
            format="json",
        )
        assert ok.status_code == 200

        # started_at を2分前に偽装 → duration 1分を超過
        MockResult.objects.filter(user=profile, mock_exam=exam).update(
            started_at=timezone.now() - datetime.timedelta(minutes=2)
        )
        res = client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "B"},
            format="json",
        )
        assert res.status_code == 400
        assert "制限時間" in res.content.decode()

    def test_answers_rejected_after_submit(self):
        client, _ = auth_client()
        exam = make_exam()
        client.post(f"/api/exams/{exam.id}/start/")
        question_id = exam.mock_questions.first().question_id
        client.post(f"/api/exams/{exam.id}/submit/")
        res = client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "A"},
            format="json",
        )
        assert res.status_code == 400
        assert "提出済み" in res.content.decode()

    def test_answer_upsert_no_grading_leak(self):
        client, _ = auth_client()
        exam = make_exam()
        client.post(f"/api/exams/{exam.id}/start/")
        question_id = exam.mock_questions.first().question_id
        res = client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "B"},
            format="json",
        )
        assert "correct" not in res.json()
        client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": question_id, "selected_choice_key": "A"},
            format="json",
        )
        assert MockAnswer.objects.count() == 1  # upsert
        assert MockAnswer.objects.get().selected_choice_key == "A"


class TestGrading:
    def test_full_cycle_grades_ranks_and_sections(self):
        university = University.objects.create(name="採点大学")
        c1, p1 = auth_client(display_name="満点", university=university)
        c2, p2 = auth_client(display_name="半分", university=university)
        c3, _p3 = auth_client(display_name="よそ者")
        exam = make_exam(n_questions=4)

        start_and_answer_all(c1, exam, key="A")  # 4/4
        # c2: 半分正解
        c2.post(f"/api/exams/{exam.id}/start/")
        for i, mq in enumerate(exam.mock_questions.all()):
            c2.post(
                f"/api/exams/{exam.id}/answers/",
                {
                    "question_id": mq.question_id,
                    "selected_choice_key": "A" if i < 2 else "B",
                },
                format="json",
            )
        c2.post(f"/api/exams/{exam.id}/submit/")
        start_and_answer_all(c3, exam, key="B")  # 0/4

        # 採点（＝順位・偏差値の集計）前でも、得点と解説はすぐ見られる
        before = c1.get(f"/api/exams/{exam.id}/result/").json()
        assert before["status"] == "submitted"
        assert before["score"] == 4
        assert len(before["review"]) == 4
        assert before["review"][0]["explanation"]
        # 順位・偏差値はまだ返さない（他の受験者の結果が要る）
        assert "rank" not in before
        assert "deviation_score" not in before

        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")

        r1 = MockResult.objects.get(user=p1)
        r2 = MockResult.objects.get(user=p2)
        assert (r1.score, r1.rank, r1.university_rank) == (4, 1, 1)
        assert (r2.score, r2.rank, r2.university_rank) == (2, 2, 2)
        assert r1.deviation_score > 50 > MockResult.objects.get(user__display_name="よそ者").deviation_score
        assert r1.percentile == pytest.approx(66.7, abs=0.1)
        assert r1.section_scores == {"D-5": 1.0, "D-7": 1.0}
        # c2 は order 1,2 のみ正解 = D-5/D-7 に1問ずつ → 各 0.5
        assert r2.section_scores == {"D-5": 0.5, "D-7": 0.5}

        # AnswerHistory へ context=mock で複写・習熟度は未演習のまま (spec)
        copied = AnswerHistory.objects.filter(user=p2, context="mock")
        assert copied.count() == 4
        assert set(copied.values_list("mastery_level", flat=True)) == {"unstudied"}

        body = c1.get(f"/api/exams/{exam.id}/result/").json()
        assert body["status"] == "graded"
        assert body["rank"] == 1
        assert body["deviation_score"] == r1.deviation_score
        assert len(body["review"]) == 4
        assert body["review"][0]["correct_choice_key"] == "A"

    def test_grading_is_idempotent_for_history_copy(self):
        client, profile = auth_client()
        client2, _ = auth_client()
        exam = make_exam(n_questions=2)
        start_and_answer_all(client, exam)
        start_and_answer_all(client2, exam)
        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")
        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")
        assert AnswerHistory.objects.filter(user=profile, context="mock").count() == 2


class TestScheduledExamCommand:
    def test_creates_exam_with_proportional_questions(self):
        for i in range(6):
            make_question(question_text=f"循{i}", category="循環器", blueprint_code="D-5-1)-①")
        for i in range(6):
            make_question(question_text=f"消{i}", category="消化器", blueprint_code="D-7-1)-①")
        call_command("create_scheduled_exam", "--kind", "cbt_once", "--open-now", "--count", "8")
        exam = MockExam.objects.get()
        assert exam.mock_questions.count() == 8
        areas = {
            mq.question.blueprint_code[:3] for mq in exam.mock_questions.all()
        }
        assert areas == {"D-5", "D-7"}
        assert exam.effective_status() == MockExam.Status.OPEN


class TestInternalCreateExamsEndpoint:
    """Vercel Cron / pg_cron から叩く模試の自動生成トリガ。"""

    def test_rejects_bad_token(self, client):
        res = client.post(
            "/api/internal/create-exams/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": "wrong"},
        )
        assert res.status_code in (401, 403)

    def test_valid_token_creates_scheduled_exams(self, client, settings):
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(5):
                make_question(
                    question_text=f"{exam_type}内部設問{i}", correct_choice_key="A", exam_type=exam_type
                )
        res = client.post(
            "/api/internal/create-exams/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        assert res.status_code == 200
        assert MockExam.objects.filter(kind=MockExam.Kind.MONTHLY).count() == 2

    def test_vercel_cron_get_with_bearer_secret_works(self, client, settings):
        settings.CRON_SECRET = "test-cron-secret"
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(5):
                make_question(
                    question_text=f"{exam_type}-cron設問{i}", correct_choice_key="A", exam_type=exam_type
                )
        res = client.get(
            "/api/internal/create-exams/",
            headers={"Authorization": "Bearer test-cron-secret"},
        )
        assert res.status_code == 200

    def test_creates_every_kind_even_with_an_empty_question_pool(self, client, settings):
        """問題が1問も無くても、受験できる模試一覧は用意される（仮設問で埋める）。"""
        res = client.post(
            "/api/internal/create-exams/",
            data="{}",
            content_type="application/json",
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
        )
        assert res.status_code == 200
        for kind in (MockExam.Kind.MONTHLY, MockExam.Kind.LARGE, MockExam.Kind.CBT_ONCE):
            exams = MockExam.objects.filter(kind=kind)
            assert exams.exists(), kind
            # 「受験できる」= 設問がぶら下がっている状態。
            for exam in exams:
                assert exam.mock_questions.count() == exam.question_count > 0


class TestPlaceholderQuestions:
    """本番の問題が無い間の繋ぎで作る仮設問は、模試だけに出す。

    通常の問題演習・復習・ランキングに混ざると「意味の無い設問」が
    学習体験に紛れ込むので、そこには絶対に出てはいけない。
    """

    def _create_exams(self):
        call_command("create_scheduled_exam", "--kind", "monthly", "--open-now")

    def test_placeholders_are_drafts_and_hidden_from_practice(self):
        self._create_exams()
        from quiz.models import Question

        placeholders = Question.objects.filter(question_text__startswith="【仮】")
        assert placeholders.exists()
        # published ではないので、演習・復習・ランキングの母集団に入らない。
        assert not placeholders.filter(status=Question.Status.PUBLISHED).exists()
        assert not Question.objects.published().filter(
            question_text__startswith="【仮】"
        ).exists()

    def test_placeholders_do_not_appear_in_the_practice_api(self):
        self._create_exams()
        client, _ = auth_client(grade=4)

        progress = client.get("/api/quiz/progress/").json()
        assert all(row["total"] == 0 for row in progress) or progress == []

        listed = client.get("/api/quiz/questions/?category=未分類").json()
        results = listed.get("results", listed)
        assert results == []

    def test_placeholder_exam_is_actually_takeable(self):
        self._create_exams()
        client, _ = auth_client(grade=4)
        exam = MockExam.objects.filter(kind=MockExam.Kind.MONTHLY, exam_type="CBT").first()

        assert client.post(f"/api/exams/{exam.id}/start/").status_code == 201
        body = client.get(f"/api/exams/{exam.id}/questions/").json()
        assert len(body["questions"]) == exam.question_count

    def test_placeholders_are_reused_instead_of_piling_up(self):
        from quiz.models import Question

        self._create_exams()
        first = Question.objects.filter(question_text__startswith="【仮】").count()
        MockExam.objects.all().delete()
        self._create_exams()
        assert Question.objects.filter(question_text__startswith="【仮】").count() == first


class TestScheduledExamIdempotency:
    """Vercel Cron から毎日叩いても、同じ日付分は重複作成しない。"""

    def test_repeated_monthly_runs_never_duplicate_the_same_date(self):
        """--open-now/--start は明示的な上書きとして冪等性チェックを飛ばす
        （デモ用）ので、ここでは実際の Cron 呼び出しと同じ「無指定」で叩く。

        1回目で今月分（即開催）、2回目で翌月分（予約）が作られ、3回目以降は
        どちらも作成済みなので何も増えない。"""
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(10):
                make_question(
                    question_text=f"{exam_type}冪等設問{i}", correct_choice_key="A", exam_type=exam_type
                )
        for _ in range(3):
            call_command("create_scheduled_exam", "--kind", "monthly")

        rows = MockExam.objects.filter(kind=MockExam.Kind.MONTHLY, exam_type="CBT")
        dates = [e.start_at.date() for e in rows]
        assert len(dates) == len(set(dates))  # 同じ日付の重複が無い
        assert len(dates) == 2  # 今月分 + 翌月分だけ


class TestMonthlyBackfill:
    """今月分の月次実力テストが無ければ即開催で作る（Cron導入直後に
    「受験できる模試が1件も無い」状態が続かないようにする）。"""

    def _seed(self):
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(20):
                make_question(
                    question_text=f"{exam_type}穴埋め設問{i}", correct_choice_key="A", exam_type=exam_type
                )

    def test_first_run_creates_an_exam_open_right_now(self):
        self._seed()
        call_command("create_scheduled_exam", "--kind", "monthly")

        exams = MockExam.objects.filter(kind=MockExam.Kind.MONTHLY)
        assert exams.count() == 2
        for exam in exams:
            assert exam.effective_status() == MockExam.Status.OPEN
            # 数日で閉じず、月末まで受けられる。
            assert exam.end_at > timezone.now() + datetime.timedelta(days=1)

    def test_second_run_schedules_next_month_instead_of_duplicating(self):
        self._seed()
        call_command("create_scheduled_exam", "--kind", "monthly")
        call_command("create_scheduled_exam", "--kind", "monthly")

        exams = MockExam.objects.filter(kind=MockExam.Kind.MONTHLY, exam_type="CBT")
        # 今月分（即開催）と翌月分（予約）の2本になり、重複はしない。
        assert exams.count() == 2
        assert exams.filter(start_at__gt=timezone.now()).count() == 1


class TestCbtOnceDefaults:
    """CBT模試（生涯1回）の既定値: 実際のCBTに合わせて4年生のみ・320問構成。"""

    def test_default_targets_grade_4_only(self):
        for i in range(5):
            make_question(question_text=f"CBT既定設問{i}", correct_choice_key="A", exam_type="CBT")
        call_command("create_scheduled_exam", "--kind", "cbt_once", "--open-now")
        exam = MockExam.objects.get(kind=MockExam.Kind.CBT_ONCE)
        assert exam.target_grade_min == 4
        assert exam.target_grade_max == 4


class TestCbtOnceExam:
    """CBT模試（生涯1回）: 提出と同時に個別採点され、二度目は受験できない。"""

    def test_immediate_grading_and_single_attempt(self):
        client, profile = auth_client(grade=3)
        exam = make_exam(n_questions=4, kind=MockExam.Kind.CBT_ONCE, exam_type="CBT")
        start_and_answer_all(client, exam)

        result = MockResult.objects.get(user=profile, mock_exam=exam)
        assert result.score == 4  # all answered "A" == correct_choice_key
        assert result.irt_theta is not None
        assert result.irt_scaled_score is not None
        assert result.points_delta is None  # CBT模試はポイント対象外

        res = client.get(f"/api/exams/{exam.id}/result/")
        assert res.status_code == 200
        assert res.json()["status"] == "graded"
        assert res.json()["irt_scaled_score"] == result.irt_scaled_score

        other_exam = make_exam(n_questions=2, kind=MockExam.Kind.CBT_ONCE, exam_type="CBT")
        blocked = client.post(f"/api/exams/{other_exam.id}/start/")
        assert blocked.status_code == 400


class TestMonthlyPoints:
    def test_grading_awards_points_and_updates_rank_pool(self):
        exam = make_exam(n_questions=4, kind=MockExam.Kind.MONTHLY, exam_type="CBT")
        c1, p1 = auth_client()
        c2, p2 = auth_client()
        start_and_answer_all(c1, exam, key="A")  # 全問正解
        start_and_answer_all(c2, exam, key="B")  # 全問不正解（correct_choice_keyはA）

        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")
        p1.refresh_from_db()
        p2.refresh_from_db()

        assert p1.ranked_matches == 1
        assert p2.ranked_matches == 1
        r1 = MockResult.objects.get(user=p1, mock_exam=exam)
        r2 = MockResult.objects.get(user=p2, mock_exam=exam)
        assert r1.points_delta > r2.points_delta
        # 累計ポイントは0スタート（D の 0%）。下限は0なので負けても0未満にならない。
        assert p1.points == max(0, STARTING_POINTS + r1.points_delta)
        assert p2.points == max(0, STARTING_POINTS + r2.points_delta)


class TestLargeExamDetail:
    def test_section_deviation_and_distribution(self):
        exam = make_exam(n_questions=4, kind=MockExam.Kind.LARGE, exam_type="KOKUSHI")
        c1, p1 = auth_client()
        c2, p2 = auth_client()
        start_and_answer_all(c1, exam, key="A")
        start_and_answer_all(c2, exam, key="B")
        call_command("grade_mock_exam", "--exam-id", exam.id, "--force")

        r1 = MockResult.objects.get(user=p1, mock_exam=exam)
        assert r1.points_delta is None  # 大型模試はポイント対象外
        assert r1.section_deviation_scores  # 分野別偏差値が入っている
        assert r1.score_distribution["buckets"]
        assert r1.score_distribution["my_bucket"] is not None


class TestPointsRanking:
    def test_only_ranked_users_are_listed(self):
        client, profile = auth_client()
        unranked_client, _ = auth_client()  # ranked_matches=0 のまま
        profile.points = 1200
        profile.ranked_matches = 3
        profile.save(update_fields=["points", "ranked_matches"])

        res = client.get("/api/ranking/points/")
        assert res.status_code == 200
        body = res.json()
        assert len(body["entries"]) == 1  # 未ランクのユーザーは含まれない
        assert body["me"]["eligible"] is True
        assert body["me"]["tier"] == "SS"  # 母集団1人なら自分が最上位


class TestPointsRankingScope:
    def test_university_scope_filters_and_reports_reason_when_unset(self):
        from accounts.models import University

        uni = University.objects.create(name="ランキング大学")
        client, profile = auth_client(university=uni)
        profile.points = 1100
        profile.ranked_matches = 2
        profile.save(update_fields=["points", "ranked_matches"])

        other_client, other = auth_client()  # 別大学（未設定）、こちらもランク対象
        other.points = 1300
        other.ranked_matches = 1
        other.save(update_fields=["points", "ranked_matches"])

        res = client.get("/api/ranking/points/?scope=university")
        assert res.status_code == 200
        body = res.json()
        assert len(body["entries"]) == 1  # 他大学のユーザーは含まれない
        assert body["entries"][0]["display_name"] != ""

        no_uni_client, _ = auth_client()
        res2 = no_uni_client.get("/api/ranking/points/?scope=university")
        assert res2.json()["me"]["eligible"] is False


class TestExamGradeGating:
    """自分が受ける試験の模試だけが一覧に出ること。

    CBTを受けるのは4年生まで、そこから先は国試に向かうので、4年生以下には
    国試の模試を、5年生以上にはCBTの模試を出さない。
    """

    def _create_monthly(self):
        # 出題プールが空だとコマンドが失敗するので、両方の試験種別を用意する。
        for exam_type in ("CBT", "KOKUSHI"):
            for i in range(40):
                make_question(
                    question_text=f"{exam_type}プール設問{i}",
                    correct_choice_key="A",
                    exam_type=exam_type,
                )
        call_command("create_scheduled_exam", "--kind", "monthly", "--open-now")
        return {e.exam_type: e for e in MockExam.objects.filter(kind=MockExam.Kind.MONTHLY)}

    def test_cbt_exam_targets_grades_1_to_4(self):
        exams = self._create_monthly()
        cbt = exams["CBT"]
        assert cbt.target_grade_min is None  # 下限なし = 1年生から
        assert cbt.target_grade_max == 4

    def test_kokushi_exam_targets_the_fifth_year_and_up(self):
        exams = self._create_monthly()
        kokushi = exams["KOKUSHI"]
        assert kokushi.target_grade_min == 5
        assert kokushi.target_grade_max is None  # 上限なし = 6年生まで
        assert not kokushi.is_open_for(4)
        assert kokushi.is_open_for(5)

    @pytest.mark.parametrize("grade", [1, 2, 3, 4])
    def test_up_to_fourth_year_sees_only_cbt(self, grade):
        self._create_monthly()
        client, _ = auth_client(grade=grade)
        types = {e["exam_type"] for e in client.get("/api/exams/").json()}
        assert types == {"CBT"}

    @pytest.mark.parametrize("grade", [5, 6])
    def test_fifth_year_and_up_sees_only_kokushi(self, grade):
        self._create_monthly()
        client, _ = auth_client(grade=grade)
        types = {e["exam_type"] for e in client.get("/api/exams/").json()}
        assert types == {"KOKUSHI"}

    def test_a_user_without_a_grade_sees_every_exam(self):
        """学年未設定のうちは絞り込まない（マイページで設定するまでの間）。"""
        self._create_monthly()
        client, _ = auth_client(grade=None)
        types = {e["exam_type"] for e in client.get("/api/exams/").json()}
        assert types == {"CBT", "KOKUSHI"}


class TestExamListSelfHeal:
    """模試が1件も無い環境でも、一覧を開けば受験できる回が用意されること。

    生成は Cron に任せているが、Cron が未設定・失敗しているとユーザーには
    「受験できる模試はありません」しか出ない。一覧側で埋め合わせる。
    """

    def test_the_list_creates_the_exams_when_none_exist(self):
        client, _ = auth_client(grade=4)
        assert MockExam.objects.count() == 0

        rows = client.get("/api/exams/").json()

        assert rows, "模試が1件も無い状態でも一覧は空にならないこと"
        assert MockExam.objects.exists()
        # 受験ボタンが出るように、いま受けられる回が含まれること
        assert any(r["status"] == "open" for r in rows)
        # 出題数ぶんの問題がひも付いていること（仮設問で埋まる）
        for exam in MockExam.objects.all():
            assert exam.mock_questions.count() == exam.question_count > 0

    def test_a_created_exam_is_actually_startable(self):
        client, _ = auth_client(grade=4)
        rows = client.get("/api/exams/").json()
        openable = next(r for r in rows if r["status"] == "open")

        assert client.post(f"/api/exams/{openable['id']}/start/").status_code == 201
        body = client.get(f"/api/exams/{openable['id']}/questions/").json()
        assert len(body["questions"]) == openable["question_count"]

    @pytest.mark.parametrize("grade", [1, 2, 3, 4, 5, 6])
    def test_every_grade_gets_something_to_take(self, grade):
        client, _ = auth_client(grade=grade)
        rows = client.get("/api/exams/").json()
        assert any(r["status"] == "open" for r in rows), f"{grade}年が受験できる模試が無い"

    def test_it_does_not_keep_creating_exams_on_every_request(self):
        client, _ = auth_client(grade=4)
        client.get("/api/exams/")
        before = MockExam.objects.count()

        client.get("/api/exams/")
        client.get("/api/exams/")

        assert MockExam.objects.count() == before

    def test_it_leaves_an_existing_open_exam_alone(self):
        client, _ = auth_client(grade=4)
        exam = make_exam()

        client.get("/api/exams/")

        assert list(MockExam.objects.values_list("id", flat=True)) == [exam.id]



class TestResultIsAvailableRightAfterSubmitting:
    """提出したら、順位の集計を待たずに得点・正誤・解説を見られること。

    順位や偏差値は他の受験者の結果がそろうまで出せないが、復習は待たせる
    ほど遠ざかるので分けて返す。
    """

    def submit(self, grade=4):
        client, profile = auth_client(grade=grade)
        exam = make_exam(n_questions=4)
        start_and_answer_all(client, exam, key="A")  # 全問正解
        return client, exam

    def test_score_and_explanations_come_back_before_grading(self):
        client, exam = self.submit()

        body = client.get(f"/api/exams/{exam.id}/result/").json()

        assert body["status"] == "submitted"
        assert body["score"] == 4
        assert body["max_score"] == 4
        assert len(body["review"]) == 4
        for row in body["review"]:
            assert row["correct"] is True
            assert row["my_choice"] == "A"
            assert row["correct_choice_key"] == "A"
            assert row["explanation"]

    def test_a_wrong_answer_is_marked_and_unanswered_is_distinguished(self):
        client, profile = auth_client(grade=4)
        exam = make_exam(n_questions=4)
        client.post(f"/api/exams/{exam.id}/start/")
        questions = client.get(f"/api/exams/{exam.id}/questions/").json()["questions"]
        # 1問だけ間違え、1問は答えない
        client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": questions[0]["id"], "selected_choice_key": "A"},
            format="json",
        )
        client.post(
            f"/api/exams/{exam.id}/answers/",
            {"question_id": questions[1]["id"], "selected_choice_key": "B"},
            format="json",
        )
        client.post(f"/api/exams/{exam.id}/submit/")

        review = client.get(f"/api/exams/{exam.id}/result/").json()["review"]

        assert [r["correct"] for r in review] == [True, False, False, False]
        assert [r["answered"] for r in review] == [True, True, False, False]
        assert review[2]["my_choice"] == ""

    def test_the_ranking_is_not_leaked_before_grading(self):
        client, exam = self.submit()
        body = client.get(f"/api/exams/{exam.id}/result/").json()
        for key in ("rank", "deviation_score", "percentile", "university_rank"):
            assert key not in body

    def test_it_says_when_the_ranking_becomes_available(self):
        """成績は翌月1日にランキングタブで見られる、と案内するための日付。"""
        import datetime

        client, exam = self.submit()
        body = client.get(f"/api/exams/{exam.id}/result/").json()

        available = datetime.datetime.fromisoformat(body["ranking_available_at"])
        end = timezone.localtime(exam.end_at)
        assert available.day == 1
        assert (available.year, available.month) == (
            (end.year + 1, 1) if end.month == 12 else (end.year, end.month + 1)
        )
        assert available > end

    def test_the_review_carries_what_the_practice_screen_needs(self):
        """見直しの設問をそのまま問題演習に渡して解き直せること。"""
        client, exam = self.submit()
        row = client.get(f"/api/exams/{exam.id}/result/").json()["review"][0]
        for key in ("question_id", "category", "exam_type", "difficulty", "choices"):
            assert key in row, key
        assert len(row["choices"]) >= 2
        assert all({"key", "text"} <= set(c) for c in row["choices"])

    def test_an_unsubmitted_exam_still_says_grading(self):
        client, _ = auth_client(grade=4)
        exam = make_exam(n_questions=4)
        client.post(f"/api/exams/{exam.id}/start/")

        body = client.get(f"/api/exams/{exam.id}/result/").json()

        assert body["status"] == "grading"
        assert "review" not in body
