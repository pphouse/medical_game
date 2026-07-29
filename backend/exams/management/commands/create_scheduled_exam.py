"""定期開催模試の自動生成 (spec フェーズ5: 毎月第1土曜など).

    python manage.py create_scheduled_exam                # 次の第1土曜 10:00 JST
    python manage.py create_scheduled_exam --start 2026-08-01T10:00:00+09:00 \
        --count 100 --duration 120 --title "8月CBT模試"
    python manage.py create_scheduled_exam --open-now --count 20   # デモ用

問題は published/public から、CBT 出題基準の構成比に近づけるため
blueprint の area（なければカテゴリ）ごとの問題数比で比例配分して抽選する。
"""

import datetime
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from exams.management.commands.grade_mock_exam import area_of
from exams.models import MockExam, MockQuestion
from quiz.models import Question


def next_first_saturday(now):
    """来月以降で最初に来る「第1土曜 10:00 JST」を返す。"""
    tz = datetime.timezone(datetime.timedelta(hours=9))
    local = now.astimezone(tz)
    year, month = local.year, local.month
    for _ in range(2):
        first = datetime.datetime(year, month, 1, 10, 0, tzinfo=tz)
        days_until_saturday = (5 - first.weekday()) % 7
        candidate = first + datetime.timedelta(days=days_until_saturday)
        if candidate > local:
            return candidate
        month += 1
        if month == 13:
            month, year = 1, year + 1
    raise AssertionError("unreachable")


class Command(BaseCommand):
    help = "MockExam + MockQuestion を自動生成する（分野比率は保有問題の構成比で比例配分）"

    def add_arguments(self, parser):
        parser.add_argument("--title", default=None)
        parser.add_argument("--start", default=None, help="ISO8601 (省略時: 次の第1土曜10:00 JST)")
        parser.add_argument("--count", type=int, default=100)
        parser.add_argument("--duration", type=int, default=120, help="分")
        parser.add_argument("--window-hours", type=int, default=12, help="受験可能時間帯の長さ")
        parser.add_argument("--grade-min", type=int, default=None)
        parser.add_argument("--grade-max", type=int, default=None)
        parser.add_argument("--open-now", action="store_true", help="今すぐ受験可にする（デモ用）")

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        if options["open_now"]:
            start = now - datetime.timedelta(minutes=1)
        elif options["start"]:
            start = datetime.datetime.fromisoformat(options["start"])
            if timezone.is_naive(start):
                raise CommandError("--start はタイムゾーン付きで指定してください")
        else:
            start = next_first_saturday(now)
        end = start + datetime.timedelta(hours=options["window_hours"])

        pool = list(
            Question.objects.published().filter(visibility=Question.Visibility.PUBLIC)
        )
        count = options["count"]
        if len(pool) < count:
            raise CommandError(
                f"published/public の問題が不足しています（{len(pool)}/{count}問）"
            )

        # area（なければカテゴリ）ごとに比例配分して抽選 (spec: CBT出題基準の
        # 構成比に近づける — 保有プールの構成比を採用)
        by_area = {}
        for question in pool:
            by_area.setdefault(area_of(question), []).append(question)
        picked = []
        for _area, questions in sorted(by_area.items()):
            share = max(1, round(count * len(questions) / len(pool)))
            random.shuffle(questions)
            picked.extend(questions[:share])
        random.shuffle(picked)
        picked = picked[:count]
        if len(picked) < count:
            remainder = [q for q in pool if q not in picked]
            random.shuffle(remainder)
            picked.extend(remainder[: count - len(picked)])

        title = options["title"] or f"{start.astimezone().strftime('%Y年%m月')} CBT全国模試"
        exam = MockExam.objects.create(
            title=title,
            start_at=start,
            end_at=end,
            question_count=count,
            duration_minutes=options["duration"],
            target_grade_min=options["grade_min"],
            target_grade_max=options["grade_max"],
        )
        MockQuestion.objects.bulk_create(
            MockQuestion(mock_exam=exam, question=question, order=i + 1)
            for i, question in enumerate(picked)
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"created MockExam #{exam.id} '{title}' {count}問 "
                f"({start.isoformat()} 〜 {end.isoformat()})"
            )
        )
