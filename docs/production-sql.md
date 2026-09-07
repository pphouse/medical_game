# 本番へ SQL を当てる

Dashboard の SQL Editor に貼るしかない、ということはない。**CLI で流せる。**
むしろ `scripts/sql/migrate_*.sql` は手で書いた代替品なので、CLI が使えるなら
Django に当てさせるほうが確実（同じ定義が二重にならない）。

## 接続文字列をどこから取るか

Supabase Dashboard → `Project Settings > Database > Connection string`。

| 用途 | ポート | 環境変数 |
|---|---|---|
| 通常のランタイム | 6543（transaction pooler） | `DATABASE_URL` |
| **マイグレーション・SQL の実行** | 5432（direct） | `MIGRATION_DATABASE_URL` |

pooler は prepared statement に対応していないので、**マイグレーションと
まとまった SQL は必ず direct（5432）で流す。**

> 接続文字列にはDBのパスワードが入っている。`~/.zshrc` に直書きせず
> `backend/.env` に置くか、その場で `read -s` で読む。シェル履歴にも
> 残さないこと（コマンドの先頭に空白を1つ入れると履歴に残らない設定が多い）。

## 方法1: Django に当てさせる（推奨）

スキーマ変更はこれが一番良い。`scripts/sql/migrate_*.sql` を流す必要が無くなる。

```bash
cd backend
python manage.py migrate --settings=config.settings_migration
```

`config/settings_migration.py` が `MIGRATION_DATABASE_URL` を読む。
`scripts/sql/migrate_*.sql` を先に流してあっても、`django_migrations` に
記録済みなので二重には当たらない（そう作ってある）。

当たっていないものを見るだけなら:

```bash
python manage.py showmigrations --settings=config.settings_migration
```

## 方法2: psql でファイルを流す

データの修正（`fix_published_kokushi.sql` など）はこちら。

```bash
psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/sql/fix_published_kokushi.sql
```

`-v ON_ERROR_STOP=1` を付けること。付けないと途中でエラーが出ても後続が走り、
`COMMIT` まで到達して**中途半端に当たった状態**になる。

psql が無ければ `brew install libpq && brew link --force libpq`。

## 方法3: Supabase CLI

`supabase/migrations/*.sql`（RLS・RPC・cron）はこれで当てる。
Django のマイグレーションや `scripts/sql/` は対象外。

```bash
supabase link --project-ref <ref>   # Personal Access Token を聞かれる
supabase db push
```

> Personal Access Token（`sbp_…`）はアカウント全体を操作できる。パスワードと
> 同じ扱いにして、コマンドライン引数に書かない（履歴に残る）。使い終わったら
> Dashboard から失効させる。

## 順番（今回のデプロイ）

`quiz.0009` が `quiz_question.choice_explanations` 列を足す。この列に書き込む
SQL を先に流すと `column ... does not exist` で落ちる。

1. **スキーマ** — 方法1（`manage.py migrate`）。CLI が使えないときだけ
   `migrate_0010_deleted_account.sql` → `migrate_quiz_0009_choice_explanations.sql`
   → `kokushi_choice_explanations.sql` の順に SQL Editor で流す
   （`kokushi_choice_explanations` は3分割版を番号順に）。
2. **データの修正** — `fix_published_kokushi.sql`。公開中の設問の誤りを直す。
3. **コードのデプロイ** — 1 より後。順番を逆にすると、新しいコードが
   `accounts_deletedaccount` を引いた時点でログイン中の全リクエストが 500 になる。

流す前に `scripts/sql/diagnose_migrations.sql` を読むと、いま何が当たって
いないかが分かる（読むだけで何も変えない）。
