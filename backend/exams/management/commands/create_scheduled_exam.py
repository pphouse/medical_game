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
            の2本を作成する。CBT版は対象学年1〜4年生、国試版は5年生以上
            － 自分の受ける試験の模試だけが一覧に出る。
  large   : 国家試験の2ヶ月前に開催する国試模試（国試のみ、対象学年5年生以上）。
            新出問題を優先し、詳細な分野別・総合の偏差値を採点コマンド側で算出する。
  cbt_once: いつでも受験できるが「ユーザーごとに生涯1回」の CBT 模試（対象学年
            4年生のみ、320問・6ブロック構成）。既存の未終了インスタンスが
            あれば重複作成しない。

問題は published/public から、本番の出題構成比（quiz/blueprint_weights）
に沿って科目ごとに比例配分して抽選する。バンクの科目ごとの問題数をその
まま比率にすると、たまたま問題を多く作った科目が模試でも多く出てしまう。
プールが足りない分は仮設問（placeholder_pool）で埋めるので、本番の問題が
まだ無くても「受験できる模試」は必ず用意される。
"""

import datetime
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from exams.models import MockExam, MockQuestion
from quiz.blueprint_weights import weights_for
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


# 仮設問の目印。question_text の先頭に付ける。
PLACEHOLDER_PREFIX = "【仮】"


def placeholder_pool(exam_type, count):
    """出題プールが足りないときに使う仮設問を、必要数そろえて返す。

    本番の問題がまだ登録されていなくても模試を「受験できる」状態にする
    ための繋ぎ。``status=draft`` で作るので Question.objects.published() /
    visible_to() には掛からず、通常の問題演習・ランキング・復習には一切
    出てこない。模試は MockQuestion 経由で直接参照するため出題はできる。

    実問題が published で入れば、そちらが優先されて仮設問は使われなくなる
    （既に作られた模試の中身は差し替わらないので、実問題が揃ったら次回の
    開催分から自然に置き換わる）。
    """
    if count <= 0:
        return []

    is_placeholder = {
        "exam_type": exam_type,
        "status": Question.Status.DRAFT,
        "question_text__startswith": PLACEHOLDER_PREFIX,
    }
    existing = list(Question.objects.filter(**is_placeholder).order_by("id")[:count])
    missing = count - len(existing)
    if missing <= 0:
        return existing

    offset = Question.objects.filter(**is_placeholder).count()
    created = Question.objects.bulk_create(
        [
            Question(
                category="未分類",
                exam_type=exam_type,
                difficulty=Question.Difficulty.NORMAL,
                # 本物の医学的な設問と紛れないよう、内容は明示的に「仮」とする。
                question_text=(
                    f"{PLACEHOLDER_PREFIX}準備中の設問です（{offset + i + 1}）。"
                    "本番の問題が登録されるまでの仮の設問のため、内容に意味はありません。"
                ),
                choices=[{"key": k, "text": f"選択肢{k}"} for k in "ABCDE"],
                correct_choice_key="A",
                explanation="仮の設問のため解説はありません。",
                status=Question.Status.DRAFT,
                source=Question.Source.OFFICIAL,
            )
            for i in range(missing)
        ]
    )
    return existing + created


def allocate(quotas, capacity, total):
    """重み ``quotas`` にしたがって ``total`` 問を科目へ割り当てる。

    ``capacity`` はその科目に実在する問題数の上限。上限に当たった科目の
    余りは、まだ余裕のある科目へ同じ比率で配り直す（配り切れなければ
    合計は total より少なくなる。呼び出し側で残りを補充する）。
    """
    allocation = {name: 0 for name in quotas}
    remaining = min(total, sum(capacity.get(n, 0) for n in quotas))
    live = {n: w for n, w in quotas.items() if w > 0 and capacity.get(n, 0) > 0}
    while remaining > 0 and live:
        weight_sum = sum(live.values())
        # 比例配分の実数を出し、整数部を配ってから端数の大きい順に1問ずつ。
        exact = {n: remaining * w / weight_sum for n, w in live.items()}
        added = 0
        for name, value in sorted(exact.items(), key=lambda kv: (-kv[1], kv[0])):
            room = capacity[name] - allocation[name]
            take = min(int(value), room)
            allocation[name] += take
            added += take
        leftover = remaining - added
        for name, _v in sorted(exact.items(), key=lambda kv: (-(kv[1] % 1), kv[0])):
            if leftover <= 0:
                break
            if allocation[name] < capacity[name]:
                allocation[name] += 1
                leftover -= 1
                added += 1
        remaining -= added
        live = {n: w for n, w in live.items() if allocation[n] < capacity[n]}
        if added == 0:
            break
    return allocation


def pick_pool(base_qs, count, *, prefer_ids=None, exclude_ids=None, exam_type=None):
    """出題構成比にしたがって抽選する。`prefer_ids` があればそれを優先母集団に
    し、不足分は `exclude_ids` を除いた残りプールから補充する。

    比率は**本番の試験の出題構成比**（quiz/blueprint_weights）で決める。
    プールの科目ごとの問題数をそのまま比率に使うと、たまたま問題を多く
    作った科目が模試でも多く出てしまうため。重み表に無い科目（仮設問の
    「未分類」など）はプール内の実数を重みとして扱い、締め出さない。
    """
    exclude_ids = exclude_ids or set()
    pool = [q for q in base_qs if q.id not in exclude_ids]
    preferred = [q for q in pool if prefer_ids is None or q.id in prefer_ids] if prefer_ids is not None else pool

    weights = weights_for(exam_type) if exam_type else {}

    def proportional(questions, n):
        by_category = {}
        for question in questions:
            by_category.setdefault(question.category, []).append(question)
        if not weights:
            # 重み表が無い試験種別では、従来どおり出題基準の area 比で配る。
            quotas = {c: len(qs) for c, qs in by_category.items()}
        else:
            quotas = {
                c: weights.get(c) or len(qs) / max(1, len(questions))
                for c, qs in by_category.items()
            }
        capacity = {c: len(qs) for c, qs in by_category.items()}
        allocation = allocate(quotas, capacity, n)
        picked = []
        for category, qs in sorted(by_category.items()):
            random.shuffle(qs)
            picked.extend(qs[: allocation[category]])
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

        picked = pick_pool(
            base_qs, min(count, len(base_qs)), prefer_ids=prefer_ids, exam_type=exam_type
        )
        if len(picked) < count:
            # 本番の問題がまだ足りなくても「受験できる模試」は用意する。
            filler = placeholder_pool(exam_type, count - len(picked))
            self.stdout.write(
                self.style.WARNING(
                    f"exam_type={exam_type} の問題が {len(picked)}/{count}問しかないため、"
                    f"残り{len(filler)}問を仮設問で埋めます"
                )
            )
            picked = picked + filler

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

        # 学年で見える模試を分ける: 4年生以下はCBT版だけ、5年生以上は国試版
        # だけ。CBTを受けるのは4年生まで、そこから先は国試に向かうので、
        # 自分の受ける試験と関係ない模試は一覧に出さない。
        flavors = [
            (Question.ExamType.CBT, None, 4, "（CBT）"),
            (Question.ExamType.KOKUSHI, 5, None, "（医師国家試験）"),
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
        picked = pick_pool(
            base_qs, min(count, len(base_qs)), exam_type=Question.ExamType.CBT
        )
        if len(picked) < count:
            filler = placeholder_pool(Question.ExamType.CBT, count - len(picked))
            self.stdout.write(
                self.style.WARNING(
                    f"CBTの問題が {len(picked)}/{count}問しかないため、"
                    f"残り{len(filler)}問を仮設問で埋めます"
                )
            )
            picked = picked + filler

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
