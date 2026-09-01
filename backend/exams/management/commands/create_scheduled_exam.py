"""定期開催模試の自動生成。

    python manage.py create_scheduled_exam --kind monthly   # 来月1日10:00 JST, 15問 x (CBT/国試)
    python manage.py create_scheduled_exam --kind large     # 国試の2ヶ月前10:00 JST, 国試模試
    python manage.py create_scheduled_exam --kind cbt_once  # 常時受験可・生涯1回のCBT模試（初回のみ作成）
    python manage.py create_scheduled_exam --kind monthly --open-now --count 5   # デモ用

冪等性: 同じ日付（monthly/large）・既存の未終了インスタンス（cbt_once）が
あれば作成をスキップする。Vercel Cron から毎日叩いても重複作成しない。

kind ごとの仕様:
  monthly : 毎月1日開催。15問・20分。「新出問題」＝過去にどの模試にも出題
            されていない問題を優先（不足時は既出からも補充）。CBT/医師国家試験
            の2本を作成する。CBT版は対象学年1〜4年生、国試版は学年制限なし
            （全学年に表示）－ 4年生以下は両方、5年生以上は国試版のみ見える。
  large   : 国家試験の2ヶ月前に開催する国試模試（国試のみ、対象学年5年生以上）。
            新出問題を優先し、詳細な分野別・総合の偏差値を採点コマンド側で算出する。
  cbt_once: いつでも受験できるが「ユーザーごとに生涯1回」の CBT 模試（対象学年
            4年生のみ、320問・6ブロック構成）。既存の未終了インスタンスが
            あれば重複作成しない。

問題は published/public から、CBT 出題基準の構成比に近づけるため
blueprint の area（なければカテゴリ）ごとの問題数比で比例配分して抽選する。
"""

import datetime
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from exams.management.commands.grade_mock_exam import area_of
from exams.models import MockExam, MockQuestion
from quiz.models import Question

JST = datetime.timezone(datetime.timedelta(hours=9))


def next_weekday_at(now, weekday, hour, minute=0):
    """来週以降で最初に来る「指定曜日 hh:mm JST」を返す（weekday: 月=0〜日=6）。"""
    local = now.astimezone(JST)
    days_ahead = (weekday - local.weekday()) % 7
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    candidate += datetime.timedelta(days=days_ahead)
    if candidate <= local:
        candidate += datetime.timedelta(days=7)
    return candidate


def next_month_first(now, hour=10):
    local = now.astimezone(JST)
    year, month = local.year, local.month + 1
    if month == 13:
        month, year = 1, year + 1
    return datetime.datetime(year, month, 1, hour, 0, tzinfo=JST)


def months_before(date_str, months):
    """'YYYY-MM-DD' から months ヶ月前の日時 10:00 JST を返す。"""
    y, m, d = (int(x) for x in date_str.split("-"))
    m -= months
    while m <= 0:
        m += 12
        y -= 1
    # 日が対象月に存在しない場合は月末に丸める（28日基準の国試日付なら通常発生しない）
    for day in range(d, 0, -1):
        try:
            return datetime.datetime(y, m, day, 10, 0, tzinfo=JST)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def pick_pool(base_qs, count, *, prefer_ids=None, exclude_ids=None):
    """area 比例配分で抽選する。`prefer_ids` があればそれを優先母集団にし、
    不足分は `exclude_ids` を除いた残りプールから補充する。"""
    exclude_ids = exclude_ids or set()
    pool = [q for q in base_qs if q.id not in exclude_ids]
    preferred = [q for q in pool if prefer_ids is None or q.id in prefer_ids] if prefer_ids is not None else pool

    def proportional(questions, n):
        by_area = {}
        for question in questions:
            by_area.setdefault(area_of(question), []).append(question)
        picked = []
        for _area, qs in sorted(by_area.items()):
            share = max(1, round(n * len(qs) / len(questions))) if questions else 0
            random.shuffle(qs)
            picked.extend(qs[:share])
        random.shuffle(picked)
        return picked[:n]

    picked = proportional(preferred, count) if preferred else []
    if len(picked) < count:
        remainder = [q for q in pool if q not in picked]
        random.shuffle(remainder)
        picked.extend(remainder[: count - len(picked)])
    return picked[:count]


class Command(BaseCommand):
    help = "MockExam + MockQuestion を自動生成する（kind ごとにスケジュール・出題ルールが異なる）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind", required=True, choices=[k for k, _ in MockExam.Kind.choices],
        )
        parser.add_argument("--title", default=None)
        parser.add_argument("--start", default=None, help="ISO8601（省略時は kind ごとの既定スケジュール）")
        parser.add_argument("--count", type=int, default=None, help="省略時は kind ごとの既定値")
        parser.add_argument("--duration", type=int, default=None, help="分。省略時は kind ごとの既定値")
        parser.add_argument("--window-hours", type=int, default=None, help="受験可能時間帯の長さ")
        parser.add_argument("--open-now", action="store_true", help="今すぐ受験可にする（デモ用）")

    def handle(self, *args, **options):
        now = timezone.now()
        kind = options["kind"]
        if kind == MockExam.Kind.CBT_ONCE:
            self._create_cbt_once(now, options)
        elif kind == MockExam.Kind.LARGE:
            self._create_one(
                now, options, kind=kind, exam_type=Question.ExamType.KOKUSHI,
                default_count=100, default_duration=180, default_window_hours=24,
                target_grade_min=5, target_grade_max=None, novel_only=True,
                default_start=lambda: months_before(settings.NATIONAL_EXAM_DATE, 2),
                default_title="国試模試（国試2ヶ月前）",
            )
        elif kind == MockExam.Kind.MONTHLY:
            self._create_monthly(now, options)
        else:  # pragma: no cover - argparse choices already restrict this
            raise CommandError("unknown kind")

    # ------------------------------------------------------------------
    def _resolve_start(self, now, options, default_start):
        if options["open_now"]:
            return now - datetime.timedelta(minutes=1)
        if options["start"]:
            start = datetime.datetime.fromisoformat(options["start"])
            if timezone.is_naive(start):
                raise CommandError("--start はタイムゾーン付きで指定してください")
            return start
        return default_start()

    @transaction.atomic
    def _create_one(
        self, now, options, *, kind, exam_type, default_count, default_duration,
        default_window_hours, target_grade_min, target_grade_max, novel_only,
        default_start, default_title, title_suffix="",
    ):
        start = self._resolve_start(now, options, default_start)
        # 冪等性: --start/--open-now の明示指定が無い定期実行では、同じ日付の
        # 分を作成済みならスキップする（Vercel Cron から毎日叩いても
        # 重複作成しないため）。
        if not options["open_now"] and not options["start"] and MockExam.objects.filter(
            kind=kind, exam_type=exam_type, start_at__date=start.date()
        ).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"{kind}/{exam_type} は {start.date()} 開催分を作成済みのためスキップします。"
                )
            )
            return None
        window_hours = options["window_hours"] or default_window_hours
        end = start + datetime.timedelta(hours=window_hours)
        count = options["count"] or default_count
        duration = options["duration"] or default_duration

        base_qs = list(
            Question.objects.published()
            .filter(visibility=Question.Visibility.PUBLIC, exam_type=exam_type)
        )
        if not base_qs:
            raise CommandError(f"exam_type={exam_type} の published/public 問題がありません")

        prefer_ids = None
        if novel_only:
            used_ids = set(
                MockQuestion.objects.filter(question__exam_type=exam_type)
                .values_list("question_id", flat=True)
            )
            prefer_ids = {q.id for q in base_qs} - used_ids
            if len(prefer_ids) < count:
                self.stdout.write(
                    self.style.WARNING(
                        f"新出問題が {len(prefer_ids)}/{count} 問しかないため、既出問題から補充します"
                    )
                )

        picked = pick_pool(base_qs, min(count, len(base_qs)), prefer_ids=prefer_ids)
        if len(picked) < count:
            self.stdout.write(
                self.style.WARNING(f"問題プールが不足しています（{len(picked)}/{count}問で作成します）")
            )

        title = options["title"] or (default_title + title_suffix)
        exam = MockExam.objects.create(
            title=title, kind=kind, exam_type=exam_type,
            start_at=start, end_at=end,
            question_count=len(picked), duration_minutes=duration,
            target_grade_min=target_grade_min, target_grade_max=target_grade_max,
        )
        MockQuestion.objects.bulk_create(
            MockQuestion(mock_exam=exam, question=question, order=i + 1)
            for i, question in enumerate(picked)
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"created MockExam #{exam.id} '{title}' ({kind}/{exam_type}) {len(picked)}問 "
                f"({start.isoformat()} 〜 {end.isoformat()})"
            )
        )
        return exam

    def _create_monthly(self, now, options):
        default_count, default_duration, default_window = 15, 20, 72
        title_base = "月次実力テスト"

        # 学年で見える模試を分ける: CBT版は1〜4年生限定、国試版は学年制限
        # なし（全学年に表示）。1〜4年生は両方見え、5年生以上は国試版だけ
        # 見える形になる。
        flavors = [
            (Question.ExamType.CBT, None, 4, "（CBT）"),
            (Question.ExamType.KOKUSHI, None, None, "（医師国家試験）"),
        ]
        local_now = now.astimezone(JST)
        for exam_type, grade_min, grade_max, suffix in flavors:
            has_this_month = MockExam.objects.filter(
                kind=MockExam.Kind.MONTHLY,
                exam_type=exam_type,
                start_at__year=local_now.year,
                start_at__month=local_now.month,
            ).exists()

            def default_start(has_this_month=has_this_month):
                # 今月分がまだ無ければ即開催にする。そうしないと、初回や
                # Cron導入直後に「受験できる模試が1件も無い（翌月分の予約
                # だけがある）」状態が最大1ヶ月続いてしまう。
                if not has_this_month:
                    return now - datetime.timedelta(minutes=1)
                return next_month_first(now)

            # 月初に開く通常の回は72時間の開催枠。今月分の穴埋めで即開催する
            # 回は、月末まで受けられるようにする（数日で閉じると結局
            # 「受験できる模試が無い」に戻ってしまうため）。
            window_hours = default_window
            if not has_this_month:
                until = next_month_first(now, hour=0)
                window_hours = max(1, round((until - now).total_seconds() / 3600))

            self._create_one(
                now, options, kind=MockExam.Kind.MONTHLY, exam_type=exam_type,
                default_count=default_count, default_duration=default_duration,
                default_window_hours=window_hours, target_grade_min=grade_min,
                target_grade_max=grade_max, novel_only=True,
                default_start=default_start, default_title=title_base, title_suffix=suffix,
            )

    @transaction.atomic
    def _create_cbt_once(self, now, options):
        existing = MockExam.objects.filter(
            kind=MockExam.Kind.CBT_ONCE,
            status__in=[MockExam.Status.SCHEDULED, MockExam.Status.OPEN],
        ).first()
        if existing:
            self.stdout.write(
                self.style.WARNING(f"CBT模試（生涯1回）は既に #{existing.id} が受験可能です。作成をスキップします。")
            )
            return existing

        start = now - datetime.timedelta(minutes=1)
        end = start + datetime.timedelta(days=365 * 100)  # 実質「常時受験可」
        count = options["count"] or 320  # 実際のCBTと同じ320問・6ブロック構成
        duration = options["duration"] or 360

        base_qs = list(
            Question.objects.published()
            .filter(visibility=Question.Visibility.PUBLIC, exam_type=Question.ExamType.CBT)
        )
        if not base_qs:
            raise CommandError("CBT の published/public 問題がありません")
        picked = pick_pool(base_qs, min(count, len(base_qs)))
        if len(picked) < count:
            self.stdout.write(
                self.style.WARNING(f"問題プールが不足しています（{len(picked)}/{count}問で作成します）")
            )

        exam = MockExam.objects.create(
            title=options["title"] or "CBT全国模試（生涯1回）",
            kind=MockExam.Kind.CBT_ONCE, exam_type=Question.ExamType.CBT,
            start_at=start, end_at=end,
            question_count=len(picked), duration_minutes=duration,
            # 実際のCBTに合わせて4年生のみ対象（1〜3年生はまだ受けられない）。
            target_grade_min=4, target_grade_max=4,
        )
        MockQuestion.objects.bulk_create(
            MockQuestion(mock_exam=exam, question=question, order=i + 1)
            for i, question in enumerate(picked)
        )
        self.stdout.write(
            self.style.SUCCESS(f"created MockExam #{exam.id} '{exam.title}' (cbt_once) {len(picked)}問（常時受験可）")
        )
        return exam
