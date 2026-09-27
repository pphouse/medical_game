"""Web Push（VAPID）で1通送る。テストでは差し替える。"""

import json

from django.conf import settings

# Push サービスが届けるのを待つ秒数。pywebpush の既定は 0 で、送った瞬間に
# ブラウザがつながっていないと捨てられる（夜8時にパソコンを閉じていた人には
# その日の通知が届かない）。3時間あれば次に開いたときに届き、21時の「連続記録が
# 途切れそう」が日付をまたいでから届くこともない。
PUSH_TTL_SECONDS = 3 * 60 * 60


def send_web_push(subscription, payload):
    from pywebpush import webpush

    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": subscription.keys,
        },
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=settings.VAPID_PRIVATE_KEY,
        vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
        ttl=PUSH_TTL_SECONDS,
    )
