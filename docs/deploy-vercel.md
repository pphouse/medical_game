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

## クイックスタート: フロントだけ動いている状態から完成させる

フロントエンドは Vercel にデプロイ済みだがバックエンドが未デプロイ、という状態から
始める場合の実手順です。この状態では画面は開けてログインもできますが、問題の読み込みで
`Unexpected token '<'` が出ます。フロントの `VITE_API_BASE_URL` が未設定で相対パス
`/api` にフォールバックし、静的ホスティングが HTML を返すためです。

### 症状から現状を切り分ける

| 確認 | コマンド / 手順 | 期待 |
|---|---|---|
| フロントが生きているか | `curl -I https://<frontend>.vercel.app` | 200 |
| バックエンドが存在するか | `curl -I https://<backend>.vercel.app` | 404 なら未作成 |
| フロントに API URL が埋まっているか | ビルド済み JS に `vercel.app/api` の文字列があるか | 無ければ未設定 |
| DB のマイグレーション状況 | Supabase SQL Editor で `select count(*) from django_migrations;` | リポジトリの migration 数以上 |

### A. DB パスワードを用意する

Supabase → **Settings → Database → Reset database password**。生成された値を控え、
接続文字列を組み立てる（**transaction pooler / 6543** を使う。5432 直結はサーバーレスに不向き）:

```
postgresql://postgres.<project-ref>:<PASSWORD>@<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

### B. バックエンドを Vercel プロジェクトとして作る

**Add New → Project → Import** でこのリポジトリを選び、

- **Project Name**: 例 `medical-game-api`
- **Root Directory**: **`backend`**（← 必ず変更する。`backend/vercel.json` が効く）
- **Framework Preset**: Other

環境変数（すべて Production）は「[環境変数チェックリスト](#環境変数チェックリスト)」の
backend 側をすべて設定する。`DJANGO_ALLOWED_HOSTS` は `.vercel.app`、
`CORS_ALLOWED_ORIGINS` はフロントの本番 URL を入れる。

`DJANGO_SECRET_KEY` と `INTERNAL_API_TOKEN` はその場で生成する:

```bash
python3 -c "import secrets,string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(64)))"
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Deploy 後、`curl -I https://<backend>.vercel.app/api/quiz/questions/` が
HTML ではなく JSON を返すことを確認する。

### C. フロントをバックエンドに向ける

フロントの Vercel プロジェクト → Settings → Environment Variables に

| 変数 | 値 |
|---|---|
| `VITE_API_BASE_URL` | `https://<backend>.vercel.app/api` |

を追加し、**Deployments → 最新 → Redeploy**。

> Vite の `import.meta.env.*` は**ビルド時に値を埋め込む**ため、環境変数を足しただけでは
> 反映されません。再デプロイが必須です。

### D. 問題バンクを投入する

`import_questions` は Postgres への直結が要るため、**ローカルから 1 コマンド**で流します
（サーバーレス側では実行しない）。

```bash
cd backend
DATABASE_URL='postgresql://postgres.<ref>:<PASSWORD>@<region>.pooler.supabase.com:6543/postgres?sslmode=require' \
DJANGO_SECRET_KEY='(何でもよい・ローカル実行用)' \
  python manage.py import_questions --file quiz/management/commands/data/cbt_batch_core_2026.json
```

`(category, question_text)` で重複判定するので、**何度流しても既存分は増えません**。
新規分だけが入ります。

### E. レビューして公開する

取り込んだ問題は **`status=pending`（審査待ち）で入り、そのままでは出題されません**（spec 2-1）。
公開するには Django admin か `POST /api/quiz/review/questions/<id>/approve/` で承認します。
医学的内容の妥当性は人の目で確認してから公開してください。

現在の状態は SQL で確認できます:

```sql
select status, count(*) from quiz_question group by status;
```

### シークレットの扱い

**サーバー専用**（フロントに置かない・共有しない・リポジトリに入れない）:
`DJANGO_SECRET_KEY` / `SUPABASE_SERVICE_ROLE_KEY` / `INTERNAL_API_TOKEN` / DB パスワード。

`SUPABASE_ANON_KEY` はフロントのバンドルに埋め込まれる前提の公開鍵です。RLS が
効いていることが安全性の前提になるので、`supabase/migrations/*.sql` の適用状況を
必ず確認してください（Django で新テーブルを追加するたびに再適用が必要）。

シークレットが漏れた疑いがあるときは、Supabase の API キーをローテートし、
`DJANGO_SECRET_KEY` と `INTERNAL_API_TOKEN` を再生成して Vercel の環境変数を
更新のうえ再デプロイします。

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
- **関数のリージョンを DB と同じリージョンに置く**。`backend/vercel.json` の `regions` で
  指定する（既定は `icn1` = ソウル。Supabase が `ap-northeast-2` のため）。
  `conn_max_age=0` でリクエストごとに接続を張り直すうえ、1リクエストで複数クエリを
  発行するため、関数と DB が別大陸にあると往復遅延がそのまま積み上がる。
  実測では `iad1`（米国東部）から `ap-northeast-2` の DB を叩くと 1 リクエスト
  2.4〜2.8 秒だったものが、`icn1` へ移すと 0.47〜0.96 秒になった（約5倍）。
  **Supabase のリージョンを変えたら `regions` も必ず合わせること。**
- ランタイムは Python 3.12（Django 6 要件。`backend/.python-version` で固定）。
- `backend/` に `pyproject.toml` を置かないこと。Vercel の Python ビルドは `uv` を使い、
  `[project]` テーブルの無い `pyproject.toml` を見つけると `uv lock` が失敗する。
  ruff/pytest の設定は `ruff.toml` / `pytest.ini` に置き、依存は `requirements.txt` に集約する。
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
