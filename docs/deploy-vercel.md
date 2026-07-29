# Vercel デプロイ手順

フロントエンド（React/Vite）とバックエンド（Django API）を **別々の Vercel
プロジェクト**としてデプロイする構成です。認証・DB は Supabase を使います。

```
[Vercel: frontend]  ──HTTPS──▶  [Vercel: backend (Django)]  ──▶  [Supabase Postgres]
  React 静的サイト                 Python サーバーレス関数            + Auth(JWKS) + Storage
```

> **前提**: Supabase プロジェクトが必要です（URL・anon key・DB 接続文字列）。
> 手順は [supabase-setup.md](./supabase-setup.md) を参照。認証は非対称署名鍵
> （RS256/ES256, JWKS）に対応済みで、`SUPABASE_URL` から JWKS を自動解決します。

---

## 0. Supabase を用意する（デプロイ前に一度だけ）

1. Supabase でプロジェクト作成。`Settings > API` と `Settings > Database` から
   値を控える（詳細は supabase-setup.md）。
2. **マイグレーションを直結接続に対して流す**（サーバーレスでは実行しない）:
   ```bash
   cd backend
   MIGRATION_DATABASE_URL='postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres?sslmode=require' \
     python manage.py migrate --settings=config.settings_migration
   ```
3. **RLS / RPC / Realtime の SQL を適用**（Django の migrate とは別系統）:
   `supabase/migrations/*.sql` を Supabase SQL Editor か `supabase db push` で適用。
   **Django で新テーブルを作るたびに `20260723000100_rls_lockdown.sql` を再適用**。
4. （任意）デモ問題を投入: `python manage.py seed_demo --with-batch`（308問を公開）。

## 1. バックエンド（Django）を Vercel にデプロイ

`backend/` を Vercel プロジェクトの **Root Directory** に設定してデプロイします。
`backend/vercel.json` が `api/index.py`（WSGI）へ全リクエストをルーティングします。

必要な環境変数（Vercel Project → Settings → Environment Variables）:

| 変数 | 例 / 備考 |
|---|---|
| `DJANGO_SECRET_KEY` | ランダム生成した値（必須） |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_ALLOWED_HOSTS` | `<backend>.vercel.app`（カスタムドメインも追加） |
| `CORS_ALLOWED_ORIGINS` | フロントの URL 例 `https://<frontend>.vercel.app` |
| `DATABASE_URL` | Supabase **transaction pooler (6543)** の接続文字列 |
| `SUPABASE_URL` | `https://<ref>.supabase.co`（JWKS 自動解決に使用） |
| `SUPABASE_ANON_KEY` | anon（publishable）key |
| `SUPABASE_SERVICE_ROLE_KEY` | service キー（**バックエンドのみ**） |
| `SUPABASE_JWT_SECRET` | レガシー HS256 のみ使う場合に設定（任意） |
| `INTERNAL_API_TOKEN` | 集計エンドポイント保護用の共有シークレット |
| `VAPID_*` | 復習リマインドを使う場合 |

CLI 例:
```bash
cd backend
vercel deploy --prod --token "$VERCEL_TOKEN"   # 初回は vercel link でプロジェクト作成
```

**注意（サーバーレスの制約）**:
- ランタイムは Python 3.12（Django 6 要件）。Vercel の Python バージョン設定を合わせる。
- DB は必ず **transaction pooler (6543)** を使う（`conn_max_age=0` 済み。サーバーレス向き）。
- `migrate` はビルドで走らせない（手順0で実施済み）。
- `/admin/` の静的ファイルは配信されない（API 用途では不要）。管理画面が必要なら
  WhiteNoise 追加を検討。
- 関数サイズが問題になる場合、runtime 依存は `requirements.txt` のみに絞ってある
  （生成スクリプト用の重い依存は `requirements-scripts.txt` に分離済み）。
- **もしサーバーレスが要件に合わなければ**、同じコードを Render / Fly.io など常駐型に
  そのままデプロイできます（標準的な Django WSGI アプリのため）。フロントは Vercel の
  ままで、`VITE_API_BASE_URL` をそのバックエンド URL に向けるだけ。

## 2. フロントエンド（Vite）を Vercel にデプロイ

`frontend/` を Root Directory に設定。`frontend/vercel.json` が SPA ルーティングを設定。

環境変数（**ビルド時にインライン化されるため、変更後は再デプロイが必要**）:

| 変数 | 値 |
|---|---|
| `VITE_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | anon key |
| `VITE_API_BASE_URL` | `https://<backend>.vercel.app/api` |
| `VITE_FEATURE_STUDENT_VERIFICATION` | 未設定（学生証機能は当面 OFF） |

CLI 例:
```bash
cd frontend
vercel deploy --prod --token "$VERCEL_TOKEN"
```

デプロイ後、バックエンドの `CORS_ALLOWED_ORIGINS` にフロントの本番 URL を追加して
再デプロイ（クロスオリジンのため）。

## 3. 定期実行（ランキング集計・模試採点・復習通知）

サーバーレスには常駐ワーカーがないため、次のいずれかで定期実行します:

- **Vercel Cron**: `/api/internal/aggregate/` を叩く Cron を設定（`X-Internal-Token` 必須）。
- **Supabase pg_cron + Edge Function**: `supabase/migrations/20260723001000_cron_schedules.sql`
  と `supabase/functions/call-internal/` を利用（`DJANGO_ORIGIN` にバックエンド URL を設定）。

模試採点 `grade_mock_exam` / リマインド `send_review_reminders` は管理コマンドなので、
Cron から内部エンドポイント経由で起動するか、スケジュール実行環境（GitHub Actions 等）
から `manage.py` を叩く運用にします。

## 環境変数チェックリスト

- backend: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS`,
  `CORS_ALLOWED_ORIGINS`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
  `SUPABASE_SERVICE_ROLE_KEY`, `INTERNAL_API_TOKEN`
- frontend: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`
- Supabase: migrate 済み + `supabase/migrations/*.sql` 適用済み
