"""内部バッチ用エンドポイントの共通認証。

呼び出し元は2通りある:

1. Supabase の pg_cron → Edge Function 経由（POST + ``X-Internal-Token``）
2. Vercel Cron（GET + ``Authorization: Bearer <CRON_SECRET>``）

Vercel Cron は GET しか送れず、ヘッダも固定なので、両方を受け付ける。
どちらのシークレットも未設定なら、誰でも叩ける状態を避けるため常に拒否する。
"""

import hmac

from django.conf import settings
from rest_framework import exceptions


def _matches(candidate, expected):
    return bool(expected) and hmac.compare_digest(candidate, expected)


def require_internal_caller(request):
    """内部バッチの呼び出し元であることを確認する。合わなければ 401。"""
    internal_token = request.headers.get("X-Internal-Token", "")
    if _matches(internal_token, settings.INTERNAL_API_TOKEN):
        return

    # Vercel Cron は "Authorization: Bearer <CRON_SECRET>" を送ってくる。
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        cron_secret = getattr(settings, "CRON_SECRET", "") or ""
        if _matches(auth[len("Bearer ") :], cron_secret):
            return

    raise exceptions.AuthenticationFailed("invalid internal token")
