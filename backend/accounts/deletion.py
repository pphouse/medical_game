"""アカウントの完全削除 (App Store Review Guideline 5.1.1(v)).

アカウントを作れるアプリは、アプリ内から削除を開始できないと審査で落ちる。
そして「消えた」と言う以上は本当に消えていないといけないので、ここでは3つ
やる。

1. 学生証画像を Supabase Storage から消す（一番機微なので最初に消す）
2. Profile を消す。ぶら下がる個人データは FK の CASCADE で一緒に消える
   （解答履歴・復習予定・模試結果・対戦・通報・通知設定・push 購読）
3. Supabase の auth.users を消す。ここを残すと本人はまだログインでき、
   次のアクセスで空の Profile が作り直されてしまう

**投稿した設問は消さない。** Question.creator / QuestionSet.creator は
SET_NULL なので、作成者だけが外れて設問は残る。他の人が解いている最中の
設問を消すと、その人の演習履歴ごと壊れるため。
"""

import requests
from django.conf import settings
from django.db import transaction

from .models import DeletedAccount, StudentVerification
from .provisioning import admin_headers, supabase_admin_configured
from .storage import delete_student_id_image


class AccountDeletionError(Exception):
    """削除しきれなかった。呼び出し側は何も消さずに終える（503）。"""


def delete_supabase_user(user_id):
    """auth.users を消す。未設定環境（ローカル・テスト）では False を返す。"""
    if not supabase_admin_configured():
        return False

    base = settings.SUPABASE_URL.rstrip("/")
    try:
        res = requests.delete(
            f"{base}/auth/v1/admin/users/{user_id}",
            headers=admin_headers(),
            timeout=15,
        )
    except requests.RequestException as exc:
        raise AccountDeletionError(f"Supabase に接続できませんでした: {exc}") from exc

    # 404 は「すでに居ない」。結果は同じなので成功として扱う。
    if res.status_code in (200, 204, 404):
        return True
    raise AccountDeletionError(
        f"Supabase のアカウント削除に失敗しました (HTTP {res.status_code})"
    )


def delete_account(profile):
    """profile とその個人データを消す。失敗したら何も消さずに例外を投げる。"""
    profile_id = profile.id

    image_paths = list(
        StudentVerification.objects.filter(
            profile_id=profile_id, image_deleted_at__isnull=True
        )
        .exclude(image_path="")
        .values_list("image_path", flat=True)
    )

    # Storage は DB のトランザクションに乗らないので巻き戻せない。学生証の
    # 画像は持っているもののなかで一番機微なので、途中で失敗しても「消えて
    # いる」側に倒す。
    for path in image_paths:
        delete_student_id_image(path)

    with transaction.atomic():
        deleted_rows, _ = profile.delete()
        DeletedAccount.objects.get_or_create(id=profile_id)
        # auth.users の削除を最後に置くのは、ここで失敗したときにローカルの
        # 削除ごと巻き戻して「ログインはできるのにデータだけ無い」という
        # 中途半端な状態を作らないため。
        auth_user_deleted = delete_supabase_user(profile_id)

    return {
        "profile_id": str(profile_id),
        "deleted_rows": deleted_rows,
        "auth_user_deleted": auth_user_deleted,
        "student_id_images": len(image_paths),
    }
