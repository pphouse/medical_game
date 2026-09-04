"""ランキングスナップショットの遅延再集計。

RankingSnapshot は aggregate_rankings が洗い替えるバッチ表で、ランキング API
はこの表しか読まない（spec 2.2）。ところが本番にはそのバッチを回すものが
無い。Vercel の serverless には常駐プロセスが無く、pg_cron も Edge Function
も設定されていないため、/api/internal/aggregate/ は誰にも叩かれないままだった。
結果、スナップショットは誰かが手で集計した時点で凍結し、その後に登録した
利用者はいくら演習してもランキングに現れない。

そこでこの表を「TTL 付きキャッシュ」として扱い、読むときに古ければその場で
再集計する。外部スケジューラに依存しないので、放っておいても順位が追従する。

同時アクセスで集計が何本も走らないよう、Postgres のアドバイザリロックで
1本に絞る。ロックを取れなかったリクエストは待たずに、少し古いスナップショット
をそのまま返す（順位表示のために利用者を待たせる価値は無い）。

/api/internal/aggregate/ は残してある。将来スケジューラを繋ぐならそちらを
叩けばよく、その場合ここは「TTL 内なので何もしない」で素通りする。
"""

import logging
import re

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from exams.models import RankingSnapshot

logger = logging.getLogger(__name__)

# アドバイザリロックのキー空間は DB 全体で共有なので、この用途専用の値を
# 決め打ちしておく（"RANK" の ASCII）。
RANKING_REFRESH_LOCK_KEY = 0x52414E4B

DEFAULT_TTL_SECONDS = 300

# aggregate_rankings が受け付ける period。クエリ文字列から素通しで渡るので、
# 集計を起動する前にここで弾く（不正値のたびに CommandError を出さないため）。
VALID_PERIOD = re.compile(r"\Aall\Z|\A\d{4}-\d{2}\Z")


def _ttl():
    return getattr(settings, "RANKING_SNAPSHOT_TTL_SECONDS", DEFAULT_TTL_SECONDS)


def snapshot_age_seconds(period):
    """period のスナップショットが何秒前のものか。1行も無ければ None。"""
    newest = RankingSnapshot.objects.filter(period=period).aggregate(
        newest=Max("computed_at")
    )["newest"]
    if newest is None:
        return None
    return (timezone.now() - newest).total_seconds()


def is_fresh(period):
    age = snapshot_age_seconds(period)
    return age is not None and age < _ttl()


def ensure_fresh(period="all"):
    """スナップショットが TTL より古ければ再集計する。再集計したら True。

    集計が落ちても例外は投げない。ランキング画面は古いデータででも出る方が
    良く、集計の失敗で画面ごと 500 にする理由が無いため。
    """
    if _ttl() < 0:  # 負値で遅延再集計を止められる（外部スケジューラ運用時）。
        return False
    if not VALID_PERIOD.match(period):
        return False
    if is_fresh(period):
        return False
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # xact 版はトランザクション終了時に自動解放されるので、
                # 集計が途中で落ちてもロックが残らない。
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s)", [RANKING_REFRESH_LOCK_KEY]
                )
                if not cursor.fetchone()[0]:
                    return False
            # 最初の判定からロック取得までの間に、別のリクエストが集計を
            # 終えているかもしれないので、取ってからもう一度見る。
            if is_fresh(period):
                return False
            call_command("aggregate_rankings", "--period", period, verbosity=0)
        return True
    except Exception:
        logger.exception("ランキングの遅延再集計に失敗した (period=%s)", period)
        return False
