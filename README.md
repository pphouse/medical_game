# medical_game — 医学生向け CBT / 国試 演習アプリ

医学生が CBT・医師国家試験の演習を「ソロ演習・復習・友だち対戦・全国模試」で
続けられる Web アプリです。React (Vite) のフロントエンドと Django REST Framework の
バックエンドで構成され、DB・認証・リアルタイム通信・画像ストレージ・定期実行に
Supabase を使います。

## 主な機能

| 機能 | 概要 |
|---|---|
| ソロ演習 | 分野別に出題。○×は自動判定、◎/△は本人だけが付けられる5段階習熟度 |
| 復習 | SM-2 ベースの間隔反復。期限が来た問題だけの復習デッキと Web Push リマインド |
| 対戦モード | 6桁ルームコードで友だちと早押しクイズ（買い切り5/10/20問、サーバー時刻で順位確定） |
| 全国模試 | 開催期間つきの模試。締切後に一括採点し、偏差値・全国/学内順位・分野別成績を返す |
| ランキング | 解いた問題数 / 正答率（初回解答のみ・100問以上）/ 大学対抗（認証済み5人以上） |
| 問題作成 | 学生証認証済みユーザーが作成 → モデレーター審査 → 公開。学内限定公開も可 |
| 問題バンク | CBT 出題基準（コアカリ）に沿った10分野58問（単問50＋四連問2セット）を同梱。増補は直接執筆 or LLM 生成 → 機械検証 → **必ず人間が審査** |

## リポジトリ構成

```
backend/    Django + DRF（採点・集計・審査などの信頼ロジックはすべてここ）
frontend/   React 19 + Vite（スマホ前提の SPA、/api を Django にプロキシ）
supabase/   SQL マイグレーション（RLS・claim_buzz RPC・pg_cron）と Edge Function
scripts/    出題基準 PDF 抽出 / LLM 問題生成 / 機械検証の CLI
schemas/    問題バッチ JSON の JSON Schema
data/       出題基準 CSV（サンプルのみコミット。全文は著作権のため生成物扱い）
docs/       アーキテクチャ / Supabase セットアップ / 問題生成の各ドキュメント
```

## セットアップ

前提: Python 3.12+ / Node.js 22+ / PostgreSQL（ローカル開発は素の Postgres でも可）

```bash
# 1) バックエンド
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env        # 値を埋める（ローカルは DATABASE_URL だけでも動く）
python manage.py migrate
python manage.py seed_demo --with-batch   # デモ問題（審査済み扱いで公開）
python manage.py runserver

# 2) フロントエンド（別ターミナル）
cd frontend
npm install
cp .env.example .env.local  # VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY
npm run dev                 # http://127.0.0.1:5173 （/api は :8000 へプロキシ）
```

Supabase 本体（Auth / Realtime / Storage / RLS / pg_cron）への接続手順は
[docs/supabase-setup.md](docs/supabase-setup.md) を参照してください。
Supabase 未設定でもバックエンド API とテストはローカル Postgres で動きます
（開発トークンは `python manage.py mint_dev_token` で発行）。

### テスト

```bash
cd backend && pytest          # 69件（認証/出題/ランキング/対戦/模試/リマインド/自作問題）
cd frontend && npm run test   # vitest（ランキング表示・対戦状態遷移）
```

CI（GitHub Actions）は ruff / pytest（Postgres サービス）/ makemigrations --check /
oxlint / vitest / vite build に加えて、**ビルド成果物に SERVICE_ROLE 文字列が
含まれないこと**を検査します（service role キーはバックエンド専用）。

## 環境変数

`backend/.env.example` / `frontend/.env.example` が正です。要点:

| 変数 | 置き場所 | 用途 |
|---|---|---|
| `DJANGO_SECRET_KEY` | backend | 本番必須（旧ハードコード鍵は漏えい扱いで廃棄済み） |
| `DATABASE_URL` | backend | 実行時 DB。Supabase は transaction pooler (6543) |
| `MIGRATION_DATABASE_URL` | backend | migrate 専用の direct 接続 (5432)。`--settings=config.settings_migration` で使用 |
| `SUPABASE_JWT_SECRET` | backend | Supabase Auth JWT (HS256) の検証鍵 |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | backend | GoTrue Admin / Storage REST の呼び出し |
| `SUPABASE_SERVICE_ROLE_KEY` | **backend のみ** | Storage 署名 URL 等。frontend 配下に置いたら CI が落ちます |
| `INTERNAL_API_TOKEN` | backend | pg_cron → Edge Function → `/api/internal/*` の共有シークレット |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` / `VAPID_ADMIN_EMAIL` | backend | 復習リマインドの Web Push |
| `ANTHROPIC_API_KEY` | scripts | LLM 問題生成 CLI |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | frontend | supabase-js（公開値のみ） |

## DB を作り直す（開発）

SQLite 時代のデータは存在しない前提（指示書 §9-1 で確認済み）なので、
スキーマは常にマイグレーションから再構築できます。

```bash
# ローカル Postgres の場合
dropdb medical_game && createdb medical_game
cd backend && python manage.py migrate
python manage.py seed_demo --with-batch     # 公開問題 115問
python manage.py seed_universities
python manage.py seed_rankings              # ランキング動作確認用のダミー履歴
python manage.py aggregate_rankings         # スナップショット集計

# Supabase の場合は migrate 後に RLS 等の SQL を必ず再適用する
#   supabase/migrations/*.sql を SQL Editor か supabase db push で適用
#   （Django の migrate は新テーブルを RLS なしで作るため、
#     20260723000100_rls_lockdown.sql の再実行が必須）
```

## アーキテクチャ / 各論ドキュメント

- [docs/architecture.md](docs/architecture.md) — 全体構成、認証、セキュリティ設計、集計定義
- [docs/supabase-setup.md](docs/supabase-setup.md) — Supabase プロジェクトの設定手順
- [docs/question-generation.md](docs/question-generation.md) — LLM 問題生成パイプライン

## 運用コマンド（抜粋）

| コマンド | 用途 |
|---|---|
| `manage.py aggregate_rankings` | ランキングスナップショット再集計（pg_cron から日次で呼ばれる想定） |
| `manage.py create_scheduled_exam` | 翌月第1土曜の模試を出題基準の分野比率で自動編成 |
| `manage.py grade_mock_exam <id>` | 締切後の一括採点（偏差値・順位・分野別成績） |
| `manage.py send_review_reminders` | 復習期限5問以上のユーザーへ Web Push（1日1回） |
| `manage.py cleanup_student_id_images` | 承認後90日を過ぎた学生証画像の削除 |
| `manage.py import_questions <json>` | 生成バッチの取り込み（**強制的に status=pending**） |
