"""Supabase Storage（学生証画像バケット）の薄いラッパ (spec フェーズ7).

- 画像は Django を経由しない: アップロードは signed upload URL、
  レビュー閲覧は短期 signed URL のみ。
- バケットは private。anon/authenticated 向けポリシーは作らない
  （署名付き URL はポリシー不要で機能する）。
"""

import requests
from django.conf import settings
from rest_framework import exceptions

SIGNED_VIEW_EXPIRES_SECONDS = 300  # レビュー用の閲覧は5分だけ有効


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)


def _headers():
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _storage_url(path):
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1{path}"


def create_signed_upload_url(object_path):
    """署名付きアップロード URL を発行する。

    返り値: {"path", "token", "signed_url"} — フロントは supabase-js の
    uploadToSignedUrl(path, token, file)、または signed_url へ直接 PUT。
    """
    if not _configured():
        raise exceptions.APIException(
            "Supabase Storage が設定されていません（SUPABASE_URL / SERVICE_ROLE_KEY）。",
            code=503,
        )
    res = requests.post(
        _storage_url(f"/object/upload/sign/{settings.STUDENT_ID_BUCKET}/{object_path}"),
        headers=_headers(),
        json={},
        timeout=15,
    )
    if res.status_code != 200:
        raise exceptions.APIException(f"signed upload URL の発行に失敗: {res.text[:200]}")
    body = res.json()
    token = body.get("token") or body.get("url", "").split("token=")[-1]
    return {
        "path": object_path,
        "token": token,
        "signed_url": _storage_url(body["url"]) if body.get("url") else None,
        "bucket": settings.STUDENT_ID_BUCKET,
    }


def create_signed_view_url(object_path, expires_in=SIGNED_VIEW_EXPIRES_SECONDS):
    """レビュー用の短期閲覧 URL (spec: レビュー時のみ短期 signed URL)."""
    if not _configured():
        return None
    res = requests.post(
        _storage_url(f"/object/sign/{settings.STUDENT_ID_BUCKET}/{object_path}"),
        headers=_headers(),
        json={"expiresIn": expires_in},
        timeout=15,
    )
    if res.status_code != 200:
        return None
    signed = res.json().get("signedURL")
    return _storage_url(signed) if signed else None


def delete_student_id_image(object_path):
    """画像を削除する。未設定環境では False（呼び出し側は削除時刻を記録しない）。"""
    if not _configured():
        return False
    res = requests.delete(
        _storage_url(f"/object/{settings.STUDENT_ID_BUCKET}"),
        headers=_headers(),
        json={"prefixes": [object_path]},
        timeout=15,
    )
    return res.status_code == 200
