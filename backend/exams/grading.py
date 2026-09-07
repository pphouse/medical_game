"""模試の採点で共通して使うロジック（バッチ採点 grade_mock_exam と、
CBT模試（生涯1回）の個別即時採点 ExamSubmitView の両方から呼ばれる）。
"""

import re
import statistics

from accounts.ranktier import apply_points_delta, exam_points_delta, speed_bonus
from exams import irt
from exams.models import ItemParameter
from quiz.models import AnswerHistory

AREA_RE = re.compile(r"^([A-F]-\d+)")


def area_of(question):
    match = AREA_RE.match(question.blueprint_code or "")
    return match.group(1) if match else question.category


def copy_answer_to_history(result, question, answer, is_correct):
    """模試の解答1件を AnswerHistory(context=mock) に複写する。

    習熟度は付けない（＝未演習のまま）。同じ模試の回で複写済みなら何もしない
    ので、提出時と採点時の両方から呼んでも二重にならない。
    """
    if AnswerHistory.objects.filter(
        user=result.user,
        question=question,
        context=AnswerHistory.Context.MOCK,
        answered_at__gte=result.mock_exam.start_at,
    ).exists():
        return
    AnswerHistory.objects.create(
        user=result.user,
        question=question,
        mastery_level=AnswerHistory.MasteryLevel.UNSTUDIED,
        correct=is_correct,
        response_time_ms=answer.response_time_ms,
        context=AnswerHistory.Context.MOCK,
    )


def copy_result_to_history(result, correct_questions):
    """提出済みの解答をまとめて AnswerHistory へ複写する。

    採点（順位・偏差値の集計）を待たずに「模試復習」で解き直せるように、
    提出した時点で呼ぶ。採点時にも同じ複写が走るが冪等。
    """
    for answer in result.answers.all():
        question = correct_questions.get(answer.question_id)
        if question is None:
            continue
        is_correct = (
            answer.selected_choice_key == question.correct_choice_key
            and answer.selected_choice_key != ""
        )
        copy_answer_to_history(result, question, answer, is_correct)


def grade_single_result(result, correct_questions):
    """1受験者分の素点・分野別正答率を算出し、AnswerHistory(context=mock) に
    複写する（習熟度は付与しない＝未演習のまま）。score/section_scores を
    result に設定するだけで save はしない（呼び出し側でまとめて更新する）。
    """
    score = 0
    per_area = {}
    for answer in result.answers.all():
        question = correct_questions.get(answer.question_id)
        if question is None:
            continue
        is_correct = (
            answer.selected_choice_key == question.correct_choice_key
            and answer.selected_choice_key != ""
        )
        score += int(is_correct)
        area = area_of(question)
        per_area.setdefault(area, [0, 0])
        per_area[area][0] += int(is_correct)
        per_area[area][1] += 1

        copy_answer_to_history(result, question, answer, is_correct)

    result.score = score
    result.section_scores = {
        area: round(c / n, 2) for area, (c, n) in sorted(per_area.items()) if n
    }
    return score, per_area


def apply_rank_stats(results):
    """複数受験者分の 全国順位/percentile/偏差値/学内順位 を算出して result に
    設定する（save はしない）。"""
    scores = [r.score for r in results]
    mean = statistics.fmean(scores)
    stdev = statistics.pstdev(scores)
    n = len(results)

    ordered = sorted(results, key=lambda r: r.score, reverse=True)
    prev_score, prev_rank = None, 0
    for i, result in enumerate(ordered, start=1):
        result.rank = prev_rank if result.score == prev_score else i
        prev_score, prev_rank = result.score, result.rank
        below = sum(1 for s in scores if s < result.score)
        result.percentile = round(below / n * 100, 1)
        result.deviation_score = (
            round(50 + 10 * (result.score - mean) / stdev, 1) if stdev else 50.0
        )

    by_university = {}
    for result in ordered:
        if result.user.university_id:
            by_university.setdefault(result.user.university_id, []).append(result)
    for members in by_university.values():
        prev_score, prev_rank = None, 0
        for i, result in enumerate(members, start=1):
            result.university_rank = prev_rank if result.score == prev_score else i
            prev_score, prev_rank = result.score, result.university_rank
    return ordered


def apply_exam_points(results):
    """週次/月次模試: 順位バケット + 解答速度ボーナスでポイントを増減する
    （spec: 対戦＋模試の合算ポイントでSS〜Dランク）。"""
    avg_times = {}
    for result in results:
        times = [a.response_time_ms for a in result.answers.all() if a.response_time_ms]
        avg_times[result.id] = statistics.fmean(times) if times else 0
    cohort_avg = statistics.fmean(avg_times.values()) if avg_times else 0

    for result in results:
        top_pct = 100 - (result.percentile or 0)
        bonus = speed_bonus(avg_times.get(result.id, 0), cohort_avg)
        delta = exam_points_delta(top_pct, speed_bonus=bonus)
        result.points_delta = delta
        apply_points_delta(result.user, delta)


def apply_large_section_deviations(results):
    """大型模試: 分野別の偏差値（section_scores の分野ごとにmean/stdevを取る）。"""
    by_area = {}
    for result in results:
        for area, rate in result.section_scores.items():
            by_area.setdefault(area, []).append((result, rate))
    for area, pairs in by_area.items():
        rates = [rate for _, rate in pairs]
        mean = statistics.fmean(rates)
        stdev = statistics.pstdev(rates)
        for result, rate in pairs:
            dev = round(50 + 10 * (rate - mean) / stdev, 1) if stdev else 50.0
            result.section_deviation_scores = {**result.section_deviation_scores, area: dev}


def apply_score_distribution(results, n_buckets=9):
    """大型模試: 得点分布ヒストグラム（自分の位置つき）を各 result に埋める。"""
    if not results:
        return
    max_score = max((r.mock_exam.question_count for r in results), default=1) or 1
    bucket_size = max(1, max_score / n_buckets)
    buckets = [0] * n_buckets

    def bucket_index(score):
        idx = int(score / bucket_size)
        return min(idx, n_buckets - 1)

    for result in results:
        buckets[bucket_index(result.score)] += 1
    for result in results:
        result.score_distribution = {
            "buckets": buckets,
            "bucket_size": round(bucket_size, 1),
            "my_bucket": bucket_index(result.score),
        }


def item_params_for(questions):
    """設問群の IRT パラメータ（較正済みならそれ、なければ難易度からの初期値）。"""
    calibrated = {
        p.question_id: {"a": p.a, "b": p.b}
        for p in ItemParameter.objects.filter(question__in=questions)
    }
    out = {}
    for question in questions:
        out[question.id] = calibrated.get(question.id) or irt.seed_item_params(question)
    return out


def apply_irt_score(result, correct_questions):
    """CBT模試（生涯1回）: 予想IRT（θ・50+10θスケール）を result に設定する。"""
    questions = list(correct_questions.values())
    params = item_params_for(questions)
    responses = []
    for answer in result.answers.all():
        question = correct_questions.get(answer.question_id)
        if question is None:
            continue
        is_correct = (
            answer.selected_choice_key == question.correct_choice_key
            and answer.selected_choice_key != ""
        )
        responses.append((question.id, is_correct))
    theta = irt.estimate_theta(responses, params)
    result.irt_theta = round(theta, 3)
    result.irt_scaled_score = irt.scaled_score(theta)
