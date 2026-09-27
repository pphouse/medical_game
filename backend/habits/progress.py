"""1日の目標・今日の進み具合・連続記録・リマインドの予定を計算する。

数え方はランキングの「解いた問題数」と同じく、ソロと復習の解答だけ
（対戦の連打や模試での水増しを除く。模試は採点のときに AnswerHistory へ
複写されるので、解いた日ではなく採点した日に入ってしまうこともある）。
そのうえで次の2つは数えない。どちらも目標を埋めるための連打を防ぐため。

- その日すでに数えた問題（同じ問題は1日1回まで）
- MIN_RESPONSE_MS 未満で答えたもの（読まずに押したとみなす）

日付の区切りは settings.TIME_ZONE（Asia/Tokyo）の0時。

リマインドの予定（reminders_for_day）は、iOS アプリが端末内に予約する分と、
Web Push を毎時送る分（habits/reminders.py）の両方がここから作る。文面と
「いつ送るか・いつやめるか」の決まりを1か所に置くため。
"""

import datetime
import logging
import zoneinfo
from dataclasses import dataclass, field

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Count, Min, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import NotificationPreference
from quiz.models import AnswerHistory, Question, ReviewSchedule

from .models import DailyGoal, ReminderLog

logger = logging.getLogger(__name__)

ONE_DAY = datetime.timedelta(days=1)

COUNTED_CONTEXTS = (AnswerHistory.Context.SOLO, AnswerHistory.Context.REVIEW)
MIN_RESPONSE_MS = 2000

# 画面で選べる目標。API はこの外の値（1〜MAX_GOAL）も受け付ける。
GOAL_CHOICES = (5, 10, 20, 30, 50)
MAX_GOAL = 100

# 連続記録をさかのぼる範囲。これより長い記録はここで打ち切る（2年あれば
# CBT から国試までをほぼ覆う）。
HISTORY_DAYS = 730

ACHIEVED, REST, MISSED = "achieved", "rest", "missed"

DEFAULT_REMINDER_HOUR = NotificationPreference._meta.get_field("preferred_hour").default
# 連続記録が途切れそうなときの夜の通知。いつもの通知がこれより遅い人には送らない。
STREAK_REMINDER_HOUR = 21
# 最後に解いた日（か目標を決めた日）からこの日数で「お休みします」を1回送り、
# そこで止める。反応の無い通知を送り続けると、通知ごとオフにされる。
PAUSE_AFTER_DAYS = 7
# 連続記録を守る通知は、守るものが2日以上あるときだけ送る。
STREAK_REMINDER_MIN = 2
# 「いつもの時刻」を決めるのに見る日数と、決めるのに要る日数。
USUAL_HOUR_DAYS = 28
USUAL_HOUR_MIN_DAYS = 3


def day_start(day):
    return datetime.datetime.combine(day, datetime.time.min, tzinfo=timezone.get_current_timezone())


def counted_answers(profile):
    return AnswerHistory.objects.filter(
        user=profile,
        context__in=COUNTED_CONTEXTS,
        response_time_ms__gte=MIN_RESPONSE_MS,
    )


def daily_counts(profile, first_day, last_day):
    """{日付: その日に数えた問題数}。1問も無い日は入らない。"""
    rows = (
        counted_answers(profile)
        .filter(
            answered_at__gte=day_start(first_day), answered_at__lt=day_start(last_day + ONE_DAY)
        )
        .annotate(day=TruncDate("answered_at", tzinfo=timezone.get_current_timezone()))
        .values("day")
        .annotate(n=Count("question", distinct=True))
    )
    return {row["day"]: row["n"] for row in rows}


class GoalTimeline:
    """目標の履歴。ある日の目標は、その日までに決めた最後の目標。"""

    def __init__(self, rows):
        # [(effective_from, questions_per_day, created_at)]、effective_from の昇順
        self.rows = rows

    @classmethod
    def for_profile(cls, profile):
        return cls(
            list(
                DailyGoal.objects.filter(profile=profile)
                .order_by("effective_from")
                .values_list("effective_from", "questions_per_day", "created_at")
            )
        )

    def on(self, day):
        if not self.rows:
            return None
        goal = self.rows[0][1]  # 最初の目標より前の日も、最初の目標で判定する
        for effective_from, value, _ in self.rows:
            if effective_from > day:
                break
            goal = value
        return goal

    def upcoming(self, day):
        """day より後に予約してある変更（目標を上げたのが達成後だった場合）。"""
        for effective_from, value, _ in self.rows:
            if effective_from > day:
                return effective_from, value
        return None

    def last_set_on(self):
        if not self.rows:
            return None
        return timezone.localdate(max(created_at for _, _, created_at in self.rows))


def evaluate_days(counts, timeline, first_day, last_day):
    """first_day〜last_day を1日ずつ見て、連続記録を数える。

    目標に届かなかった日は、連続記録があれば週（月曜はじまり）に1日だけ
    「お休み」として記録を切らさない（数には入れず、守るだけ）。同じ週の
    2日目からは途切れる。記録が0のときに届かなかった日は、お休みを使わない。
    """
    statuses = {}
    running = 0
    rest_weeks = set()
    day = first_day
    while day <= last_day:
        if counts.get(day, 0) >= timeline.on(day):
            statuses[day] = ACHIEVED
            running += 1
        else:
            week = day.isocalendar()[:2]
            if running and week not in rest_weeks:
                rest_weeks.add(week)
                statuses[day] = REST
            else:
                statuses[day] = MISSED
                running = 0
        day += ONE_DAY
    return statuses, running, rest_weeks


@dataclass
class HabitState:
    today: datetime.date
    timeline: GoalTimeline
    counts: dict
    statuses: dict = field(default_factory=dict)
    running: int = 0
    rest_weeks: set = field(default_factory=set)

    @property
    def goal(self):
        return self.timeline.on(self.today)

    @property
    def count(self):
        return self.counts.get(self.today, 0)

    @property
    def achieved(self):
        return self.goal is not None and self.count >= self.goal

    @property
    def remaining(self):
        return None if self.goal is None else max(self.goal - self.count, 0)

    @property
    def streak(self):
        return self.running + (1 if self.achieved else 0)

    @property
    def rest_available(self):
        return self.today.isocalendar()[:2] not in self.rest_weeks

    @property
    def last_study_date(self):
        return max(self.counts) if self.counts else None

    def recent_days(self, n=7):
        days = []
        for offset in range(n - 1, -1, -1):
            day = self.today - offset * ONE_DAY
            if day == self.today:
                status = ACHIEVED if self.achieved else "today"
            else:
                status = self.statuses.get(day, "none")
            days.append(
                {
                    "date": day,
                    "count": self.counts.get(day, 0),
                    "goal": self.timeline.on(day),
                    "status": status,
                }
            )
        return days


def habit_state(profile, now=None):
    today = timezone.localdate(now or timezone.now())
    timeline = GoalTimeline.for_profile(profile)
    counts = daily_counts(profile, today - HISTORY_DAYS * ONE_DAY, today)
    state = HabitState(today=today, timeline=timeline, counts=counts)
    if timeline.rows and counts:
        state.statuses, state.running, state.rest_weeks = evaluate_days(
            counts, timeline, min(counts), today - ONE_DAY
        )
    return state


def usual_hour(profile, now=None):
    """いつも勉強を始める時刻（各日の最初の解答の時の中央値）。記録が少なければ None。"""
    today = timezone.localdate(now or timezone.now())
    firsts = (
        counted_answers(profile)
        .filter(answered_at__gte=day_start(today - USUAL_HOUR_DAYS * ONE_DAY))
        .annotate(day=TruncDate("answered_at", tzinfo=timezone.get_current_timezone()))
        .values("day")
        .annotate(first=Min("answered_at"))
    )
    hours = sorted(timezone.localtime(row["first"]).hour for row in firsts)
    if len(hours) < USUAL_HOUR_MIN_DAYS:
        return None
    return hours[len(hours) // 2]


def set_daily_goal(profile, questions_per_day, now=None):
    """目標を変えて、効き始める日を返す。

    今日の目標をもう達成しているのに上げる場合だけ明日から効かせる。今日の
    達成を後から取り消さないため。下げる場合と、まだ達成していない場合は
    今日から効く。
    """
    today = timezone.localdate(now or timezone.now())
    current = GoalTimeline.for_profile(profile).on(today)
    effective_from = today
    if current is not None and questions_per_day > current:
        if daily_counts(profile, today, today).get(today, 0) >= current:
            effective_from = today + ONE_DAY
    with transaction.atomic():
        # 先の日付で予約していた変更は、今回の設定で置き換える。
        DailyGoal.objects.filter(profile=profile, effective_from__gt=effective_from).delete()
        if GoalTimeline.for_profile(profile).on(effective_from) != questions_per_day:
            DailyGoal.objects.update_or_create(
                profile=profile,
                effective_from=effective_from,
                defaults={"questions_per_day": questions_per_day},
            )
    return effective_from


def progress_after_answer(profile, answer):
    """解答した直後の今日の進み具合。解答の応答に添える。

    目標の表が無い（本番で migrate より先にデプロイされた）などで失敗しても、
    解答の記録そのものは止めない。None を返し、画面は進み具合を出さない。
    """
    try:
        with transaction.atomic():
            return _progress_after_answer(profile, answer)
    except DatabaseError:
        logger.exception("daily progress unavailable")
        return None


def _progress_after_answer(profile, answer):
    day = timezone.localdate(answer.answered_at)
    counted = counted_answers(profile).filter(
        answered_at__gte=day_start(day), answered_at__lt=day_start(day + ONE_DAY)
    )
    totals = counted.aggregate(
        after=Count("question", distinct=True),
        before=Count("question", distinct=True, filter=~Q(pk=answer.pk)),
    )
    goal = GoalTimeline.for_profile(profile).on(day)
    count = totals["after"]
    progress = {
        "date": day,
        "goal": goal,
        "count": count,
        "remaining": None if goal is None else max(goal - count, 0),
        "achieved": goal is not None and count >= goal,
        "just_achieved": goal is not None and totals["before"] < goal <= count,
    }
    if progress["just_achieved"]:
        # 達成の画面に連続日数を出す。重い計算なので達成した1回だけ。
        progress["streak"] = habit_state(profile, answer.answered_at).streak
    return progress


# --- リマインド ---------------------------------------------------------


@dataclass
class ReminderExtras:
    """文面に使う、その人の状況。"""

    due_reviews: int = 0
    exam_date: datetime.date | None = None  # 国試を選んでいる人だけ

    def exam_days(self, day):
        if self.exam_date is None:
            return None
        left = (self.exam_date - day).days
        return left if 0 < left <= 365 else None


def reminder_extras(profile, now=None):
    now = now or timezone.now()
    due = ReviewSchedule.objects.filter(
        user=profile,
        next_review_at__lte=now,
        question__in=Question.objects.visible_to(profile),
    ).count()
    exam_date = None
    if profile.resolved_exam_type == "KOKUSHI":
        try:
            exam_date = datetime.date.fromisoformat(settings.NATIONAL_EXAM_DATE)
        except (TypeError, ValueError):
            exam_date = None
    return ReminderExtras(due_reviews=due, exam_date=exam_date)


KIND_IDS = {
    ReminderLog.Kind.DAILY: 1,
    ReminderLog.Kind.STREAK: 2,
    ReminderLog.Kind.PAUSED: 3,
}


@dataclass
class Reminder:
    at: datetime.datetime
    kind: str
    template: str
    title: str
    body: str
    url: str = "/"

    @property
    def id(self):
        # 端末に予約する通知の番号。日付と種類から決めるので、予約し直しても
        # 同じ通知は同じ番号になる（32bit に収まる）。
        return int(self.at.strftime("%Y%m%d")) * 10 + KIND_IDS[self.kind]

    def as_dict(self):
        return {
            "id": self.id,
            "at": self.at,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "url": self.url,
        }


def reminder_timezone(pref):
    try:
        return zoneinfo.ZoneInfo(pref.timezone)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return timezone.get_current_timezone()


def _daily_text(state, extras, day):
    """今日の目標の通知の文面。同じ文面ばかりだと慣れて効かなくなるので日ごとに変える。

    今日すでに解き始めているなら「あと何問」が一番効くので、それを出す。
    """
    goal = state.timeline.on(day)
    if day == state.today and state.count:
        return (
            "remaining",
            "今日の目標まであと少し",
            f"あと{state.remaining}問で今日の{goal}問です。",
            "/",
        )
    candidates = [("start", f"今日の{goal}問", f"今日の{goal}問から始めましょう。", "/")]
    if day == state.today:
        if state.streak:
            candidates.append(
                ("streak", f"連続{state.streak}日", f"今日の{goal}問で記録を伸ばしましょう。", "/")
            )
        if extras.due_reviews:
            candidates.append(
                (
                    "review",
                    "復習の期限です",
                    f"期限が来た復習が{extras.due_reviews}問あります。今日の{goal}問に入れましょう。",
                    "/review",
                )
            )
    days_left = extras.exam_days(day)
    if days_left is not None:
        candidates.append(
            ("exam", f"国試まであと{days_left}日", f"今日の{goal}問を積み上げましょう。", "/")
        )
    candidates.append(("one", "1問だけでも", f"開いて1問解けば、{goal}問はすぐです。", "/"))
    return candidates[day.toordinal() % len(candidates)]


def _streak_text(state):
    if state.rest_available:
        return (
            "streak_rest",
            f"連続{state.streak}日",
            f"今日の目標まであと{state.remaining}問。届かなければ今週のお休みを使います。",
            "/",
        )
    return (
        "streak_last",
        f"連続{state.streak}日が途切れそうです",
        f"今日の目標まであと{state.remaining}問です。",
        "/",
    )


PAUSED_TEXT = (
    "paused",
    "通知をお休みします",
    "しばらく通知を止めます。また始めるときはアプリを開いてください。",
    "/",
)


def reminders_for_day(state, extras, pref, day):
    """day に送る通知。目標が無い人・通知を止める日を過ぎた人には無い。"""
    if state.goal is None:
        return []
    last_activity = [d for d in (state.last_study_date, state.timeline.last_set_on()) if d]
    idle_days = (day - max(last_activity)).days
    if idle_days > PAUSE_AFTER_DAYS:
        return []
    tz = reminder_timezone(pref)
    at = datetime.datetime.combine(day, datetime.time(pref.preferred_hour), tzinfo=tz)
    if idle_days == PAUSE_AFTER_DAYS:
        return [Reminder(at, ReminderLog.Kind.PAUSED, *PAUSED_TEXT)]
    if day == state.today and state.achieved:
        return []
    reminders = [Reminder(at, ReminderLog.Kind.DAILY, *_daily_text(state, extras, day))]
    if (
        day == state.today
        and state.streak >= STREAK_REMINDER_MIN
        and pref.preferred_hour < STREAK_REMINDER_HOUR
    ):
        evening = datetime.datetime.combine(day, datetime.time(STREAK_REMINDER_HOUR), tzinfo=tz)
        reminders.append(Reminder(evening, ReminderLog.Kind.STREAK, *_streak_text(state)))
    return reminders


def reminder_plan(state, extras, pref, now=None):
    """これから PAUSE_AFTER_DAYS 日ぶんの通知（iOS アプリが端末内に予約する）。

    アプリを開くたび・解くたびに作り直すので、解いている人には「お休みします」
    は届かない。
    """
    if pref is None or not pref.enabled:
        return []
    now = now or timezone.now()
    reminders = []
    for offset in range(PAUSE_AFTER_DAYS + 1):
        reminders += reminders_for_day(state, extras, pref, state.today + offset * ONE_DAY)
    return [r for r in reminders if r.at > now]


def habit_payload(profile, now=None):
    """GET /api/habits/today/ の中身。ホームの目標カードとリマインドの設定画面が使う。"""
    now = now or timezone.now()
    state = habit_state(profile, now)
    pref = NotificationPreference.objects.filter(profile=profile).first()
    upcoming = state.timeline.upcoming(state.today)
    plan = []
    if pref is not None and pref.enabled and state.goal is not None:
        plan = [r.as_dict() for r in reminder_plan(state, reminder_extras(profile, now), pref, now)]
    return {
        "date": state.today,
        "goal": state.goal,
        "count": state.count,
        "remaining": state.remaining,
        "achieved": state.achieved,
        "streak": state.streak,
        "rest_available": state.rest_available,
        "days": state.recent_days(),
        "upcoming_goal": (
            {"questions_per_day": upcoming[1], "effective_from": upcoming[0]} if upcoming else None
        ),
        "goal_choices": list(GOAL_CHOICES),
        "reminder": {
            "enabled": bool(pref and pref.enabled),
            "hour": pref.preferred_hour if pref else DEFAULT_REMINDER_HOUR,
        },
        "suggested_hour": usual_hour(profile, now),
        "reminders": plan,
    }
