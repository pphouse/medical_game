#!/usr/bin/env python3
"""SQLファイルを本番DBへまとめて流す。

Supabase の SQL Editor は1クエリ1MB前後が上限で、分割したファイルを1本ずつ
貼るのが手間なので、CLIから順に流せるようにする。

つなぎ方は2つある。どちらか片方の環境変数を用意すれば動く。

1. psql（推奨。分割前のファイルもそのまま流せる）
     export DATABASE_URL='postgresql://postgres.xxxx:PASSWORD@aws-0-...pooler.supabase.com:5432/postgres'
   Supabase の Project Settings → Database → Connection string。
   Session pooler の方が通りやすい。

2. Supabase Management API（psql を入れたくないとき）
     export SUPABASE_ACCESS_TOKEN='sbp_...'   # アカウント設定 → Access Tokens
     export SUPABASE_PROJECT_REF='cdeqtmskournriqxjoad'
   このトークンはアカウント全体を操作できる。パスワードと同じ扱いにして、
   使い終わったら失効させること。シェル履歴に残さないよう、export では
   なくファイルに置いて `set -a; . ./.env; set +a` で読むのが安全。

使い方:
    python scripts/run_sql.py scripts/sql/apply_categories.sql
    python scripts/run_sql.py scripts/sql/repair_question_text_*.sql
    python scripts/run_sql.py --dry-run scripts/sql/*.sql
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.supabase.com/v1/projects/{ref}/database/query"


def run_psql(path: str, url: str) -> tuple[bool, str]:
    out = subprocess.run(
        ["psql", url, "-v", "ON_ERROR_STOP=1", "-f", path],
        capture_output=True,
        text=True,
    )
    return out.returncode == 0, (out.stdout + out.stderr).strip()


def run_api(path: str, token: str, ref: str) -> tuple[bool, str]:
    sql = open(path, encoding="utf-8").read()
    req = urllib.request.Request(
        API.format(ref=ref),
        data=json.dumps({"query": sql}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as res:
            body = res.read().decode()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:500]}"
    except urllib.error.URLError as e:
        return False, f"接続できない: {e.reason}"
    try:
        rows = json.loads(body)
    except json.JSONDecodeError:
        return True, body[:500]
    if isinstance(rows, list):
        return True, "\n".join(json.dumps(r, ensure_ascii=False) for r in rows[:20])
    return True, json.dumps(rows, ensure_ascii=False)[:500]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="流すSQLファイル（並べた順に実行）")
    parser.add_argument("--dry-run", action="store_true", help="流さずに順番だけ出す")
    args = parser.parse_args()

    # 並べ替えない。指定された順に流す。シェルの * 展開は元から名前順なので
    # 並べ替える必要が無く、逆に手で順番を指定したときに壊れる。
    files = args.files
    db_url = os.environ.get("DATABASE_URL")
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    ref = os.environ.get("SUPABASE_PROJECT_REF")

    has_psql = subprocess.run(["which", "psql"], capture_output=True).returncode == 0
    if db_url and has_psql:
        how, runner = "psql", lambda p: run_psql(p, db_url)
    elif token and ref:
        how, runner = "Management API", lambda p: run_api(p, token, ref)
    elif db_url and not has_psql:
        raise SystemExit(
            "DATABASE_URL はあるが psql が無い。psql を入れるか、"
            "SUPABASE_ACCESS_TOKEN と SUPABASE_PROJECT_REF を設定する。"
        )
    else:
        raise SystemExit(
            "接続情報が無い。DATABASE_URL か、"
            "SUPABASE_ACCESS_TOKEN + SUPABASE_PROJECT_REF を設定する。"
            "\n詳しくは このファイルの先頭のコメント を参照。"
        )

    print(f"接続方法: {how}   ファイル {len(files)}本\n")
    if args.dry_run:
        for i, f in enumerate(files, 1):
            print(f"  {i:2d}. {f}  ({os.path.getsize(f) / 1024:.0f}KB)")
        return 0

    failed = []
    for i, path in enumerate(files, 1):
        size = os.path.getsize(path) / 1024
        print(f"── [{i}/{len(files)}] {os.path.basename(path)} ({size:.0f}KB)")
        ok, out = runner(path)
        for line in out.splitlines():
            print(f"     {line}")
        if not ok:
            failed.append(path)
            print("     ★ 失敗。ここで止める（後続は前提が崩れるため）。")
            break

    if failed:
        print(f"\n失敗: {failed[0]}")
        print("どのファイルも何度流しても結果は同じなので、直したら最初から流し直してよい。")
        return 1
    print(f"\n{len(files)}本すべて完了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
