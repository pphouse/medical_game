"""デプロイ設定の安全側の既定値を固定するテスト。

Vercel のプレビュー環境で DJANGO_DEBUG を設定し忘れており、Django の
デバッグページ（設定値・トレースバック・Cookie を含む）がそのまま
配信されていた。原因は環境変数が無いときの既定が True だったこと。
同じ倒れ方を二度としないようにここで固定する。

settings を同一プロセスで再読み込みすると後続のテストに状態が残るので、
毎回サブプロセスで読み込んで隔離する。
"""

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# .env があるとローカルの設定に引きずられるので読ませない。
PROBE = """
import json, os, environ
environ.Env.read_env = staticmethod(lambda *a, **k: None)
import django
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
try:
    django.setup()
except Exception as exc:
    print(json.dumps({"error": type(exc).__name__}))
else:
    from django.conf import settings
    print(json.dumps({
        "debug": settings.DEBUG,
        "allowed_hosts": list(settings.ALLOWED_HOSTS),
        "has_secret": bool(settings.SECRET_KEY),
    }))
"""


def load_settings(**env):
    """指定した環境変数だけで settings を読み込み、結果を返す。"""
    clean = {
        k: v
        for k, v in {
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp",
            **env,
        }.items()
        if v is not None
    }
    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND,
        env=clean,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_debug_is_off_when_the_env_var_is_missing():
    assert load_settings(DJANGO_SECRET_KEY="x")["debug"] is False


def test_secret_key_is_required_when_debug_is_off():
    assert load_settings()["error"] == "ImproperlyConfigured"


def test_debug_can_still_be_enabled_explicitly_for_local_dev():
    result = load_settings(DJANGO_DEBUG="true")
    assert result["debug"] is True
    # DEBUG のときだけ SECRET_KEY 無しでも起動できる（ローカルの利便性）
    assert result["has_secret"] is True


def test_allowed_hosts_does_not_default_to_wildcard():
    # "*" を既定にすると Host ヘッダ検証が無効になる
    assert "*" not in load_settings(DJANGO_SECRET_KEY="x")["allowed_hosts"]
