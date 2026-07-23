# Supabase セットアップ手順

このアプリは Supabase を以下の範囲で使います（指示書 1.1 の決定事項）。

| Supabase 機能 | 用途 |
|---|---|
| Postgres | 唯一の DB（SQLite は廃止） |
| Auth | ユーザー認証（メール+パスワード / Magic Link） |
| Realtime | 対戦モードの出題・早押し結果のブロードキャスト |
| Storage | 学生証画像（private bucket `student-ids`） |
| RLS | 対戦テーブル・プロフィールの直接アクセス制御、それ以外は全拒否 |
| pg_cron + Edge Functions | ランキング集計等の定期実行（Django の internal API を叩く） |

Django は**テーブルオーナー（RLS 対象外）の接続**で入り、採点・集計・審査などの
信頼が必要なロジックをすべて持ちます。フロントが supabase-js で直接触るのは
対戦系テーブルの購読と `claim_buzz` RPC、および `public_profiles` ビューのみです。

## 1. プロジェクト作成

1. https://supabase.com/dashboard で新規プロジェクトを作成（リージョンは東京推奨）。
2. `Project Settings > API` から以下を控える:
   - Project URL → `SUPABASE_URL` / `VITE_SUPABASE_URL`
   - anon key → `SUPABASE_ANON_KEY` / `VITE_SUPABASE_ANON_KEY`
   - service_role key → `SUPABASE_SERVICE_ROLE_KEY`（**バックエンドのみ。frontend/ に置かない**）
   - JWT Secret（legacy） → `SUPABASE_JWT_SECRET`
3. `Project Settings > Database` から接続文字列を控える:
   - Transaction pooler (port 6543) → `DATABASE_URL`
   - Direct connection (port 5432) → `MIGRATION_DATABASE_URL`

`backend/.env.example` を `backend/.env` にコピーして埋める。
`frontend/.env.example` を `frontend/.env.local` にコピーして埋める。

## 2. Django スキーマの適用

transaction pooler は prepared statement 非対応のため、**マイグレーションだけは
direct connection を使う**（`config/settings_migration.py` が
`MIGRATION_DATABASE_URL` を読む）:

```bash
cd backend
python manage.py migrate --settings=config.settings_migration
```

通常のランタイム（runserver 等）は `DATABASE_URL`（pooler / `conn_max_age=0`）を使う。

## 3. RLS・RPC の適用（supabase/migrations/）

Supabase 側の SQL は `supabase/migrations/*.sql` でバージョン管理する
（Django のマイグレーションとは別管理。Django が作ったテーブルに後から
RLS / grant を当てる、という関係）。

適用方法はどちらでも良い:

- **Supabase CLI**（推奨）: `supabase link --project-ref <ref>` 後に `supabase db push`
- **手動**: Dashboard の SQL Editor にファイル内容を古い順に貼り付けて実行

> **重要**: 新しい Django マイグレーションで**テーブルを追加した後**は、
> `20260723000100_rls_lockdown.sql`（冪等）を再実行して新テーブルも
> deny-by-default に入れること。

## 4. Auth 設定

1. `Authentication > Providers > Email` を有効化（パスワード + Magic Link）。
2. 開発中はメール確認を無効にすると楽（`Confirm email` を off）。
3. デモユーザーの一括作成（service role key が必要）:

```bash
python manage.py seed_supabase_users        # demo1〜demo4@example.com / demo-password-123
python manage.py seed_universities          # 医学部を持つ全大学
python manage.py seed_demo                  # サンプル問題
python manage.py seed_rankings              # ランキング用ダミー解答履歴
```

## 5. Storage（学生証画像・フェーズ7）

1. private bucket `student-ids` を作成（Public access: OFF）。
2. アップロードは Django が発行する **signed upload URL** 経由のみ
   （`POST /api/auth/student-verification/`）。バケットに anon/authenticated 向けの
   ポリシーは**作らない**こと（署名付き URL はポリシー不要で機能する）。
3. 保持期間: 却下時は即削除、承認後は90日で `cleanup_student_id_images`
   コマンドが削除する（cron 推奨・日次）。

## 6. 定期ジョブ（pg_cron + Edge Function・フェーズ3以降）

集計ロジックは Django 側に一本化し（二重管理を避ける）、pg_cron からは
Edge Function 経由で Django の internal API を叩く:

```
pg_cron ──> Edge Function `call-internal` ──> POST {DJANGO_ORIGIN}/api/internal/aggregate/
                                              (header: X-Internal-Token)
```

1. `supabase/functions/call-internal/` をデプロイ:
   ```bash
   supabase functions deploy call-internal --no-verify-jwt
   supabase secrets set DJANGO_ORIGIN=https://<your-django-host> INTERNAL_API_TOKEN=<same-as-backend-env>
   ```
2. SQL Editor で `supabase/migrations/20260723001000_cron_schedules.sql` を実行
   （`vault` にサービスキーを置き、`cron.schedule` で毎時/日次を登録する。
   ファイル内のコメントに従って `<project-ref>` を置換すること）。

## 7. ローカル開発（Supabase なし）

ローカル Postgres だけでもバックエンド開発は可能:

```bash
createdb medical_game            # postgres:postgres@127.0.0.1:5432 を想定（.env で変更可）
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
echo 'SUPABASE_JWT_SECRET=local-dev-secret' >> .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
TOKEN=$(.venv/bin/python manage.py mint_dev_token --email dev@example.com)
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/quiz/summary/
```

`mint_dev_token` は `SUPABASE_JWT_SECRET` で署名した Supabase 互換トークンを
発行する開発専用コマンド（`DJANGO_DEBUG=false` では拒否される）。
フロントのログイン画面まで通しで動かす場合は実プロジェクトが必要。

## 8. 環境変数一覧

| 変数 | 置き場所 | 用途 |
|---|---|---|
| `DJANGO_SECRET_KEY` | backend | セッション/CSRF 署名（admin 用）。旧ハードコード値は漏洩扱いで廃棄済み |
| `DATABASE_URL` | backend | pooler(6543) 接続。`conn_max_age=0` 固定 |
| `MIGRATION_DATABASE_URL` | backend | direct(5432) 接続。migrate 専用 |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | backend | Admin API / Storage API のベース URL 等 |
| `SUPABASE_SERVICE_ROLE_KEY` | backend **のみ** | auth.users 作成、Storage 署名 URL 発行 |
| `SUPABASE_JWT_SECRET` | backend | アクセストークンの HS256 検証 |
| `INTERNAL_API_TOKEN` | backend + Edge Function | /api/internal/* の保護 |
| `VAPID_PRIVATE_KEY` ほか | backend | Web Push（フェーズ6） |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | frontend | supabase-js 初期化（公開可の値のみ） |

> 2025年以降の新規プロジェクトは非対称署名（ES256/JWKS）が既定の場合がある。
> その場合は `Project Settings > API > JWT keys` で legacy HS256 secret を確認
> して使う（本バックエンドの検証は指示書どおり HS256 固定）。
