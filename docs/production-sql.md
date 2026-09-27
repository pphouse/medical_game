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

## 1日の目標と学習リマインドの表（migrate_habits_0001.sql）

`habits.0001_initial` を当てる。**PR をマージする（デプロイする）前に**
SQL Editor に1回貼る。何度流しても結果は同じで、先に流しても今のコードには
影響しない。表には RLS を掛けてある（Data API からは読めない）。

表が無いままデプロイされても解答は止まらないように作ってあるが、ホームの
目標カードとマイページの設定が出ない。

## 科目名の統一（fix_categories.sql）

演習画面の科目一覧は分野名の DISTINCT なので、正規の科目名でない分野名が
残っていると同じ科目が2行に分かれて出る（国試の「放射線」と「放射線科」、
CBT の「麻酔」と「救急・中毒・麻酔」など）。`scripts/sql/fix_categories.sql`
が次をまとめて行う。

1. 四連問（セットに属するタイプQの設問）を単問にほどく。演習画面では
   4問を順に解かせられず、印だけの四連問になっていたため。症例文を設問の
   頭に付けて（「症例文＋改行＋設問」）セットから外す。すでに症例文で
   始まる設問には付け足さないので、何度流しても二重にならない。
2. 公式の設問（同梱データにあるもの）の分野を、同梱データの分野に
   そろえる。同梱データの分野は1問ずつ確かめたもので、CI が科目名の
   正しさを見ている。
3. 同梱データに無い設問（見本・投稿）は、科目名でないときだけ直す。

マイグレーション 0014〜0017 は設問文の語で分野を決め直すため、同梱データと
食い違う設問が出る（選択肢の語に引かれて糸球体腎炎が泌尿器になる、など）。
0018 がこの SQL と同じことを migrate の最後に行うので、**migrate とこの SQL は
どちらを先に当てても、どちらか片方だけでも、結果は同じ**（使い捨てDBで
4通りの順番を試して確認済み）。

- SQL Editor に1回貼るだけ（207KB）。最後に1つの表が出るので、それを見る。
  「2.残った」が0行なら完了。
- 何度流しても結果は同じ。コードのデプロイとの順番は問わない。
- 科目立てや同梱データの分野を変えたら `python scripts/build_category_fix_sql.py`
  で作り直す。
- いまの状態は `verify_state.sql` の15行目でも分かる。

## 新しい設問を入れる（import_*.sql）

本番はデプロイで `import_questions` を流さないので、同梱データに足した設問は
SQL で入れる。`scripts/build_question_import_sql.py` が `import_questions` と
同じ変換・同じ重複判定の INSERT を書き出す（テストで行の中身まで一致を確認）。

| ファイル | 中身 |
|---|---|
| `import_cbt_basic_2026_01.sql`, `_02.sql` | CBT 基礎医学 500問（C-1〜C-5、単問のみ） |

- SQL Editor に1本ずつ貼る。順番は問わない。流すと「追加した問題／すでに
  あった問題」の表が出る。2本の「追加した問題」の合計が500なら完了。
- 何度流しても結果は同じ（本文と選択肢が同じ問題はもう入れない）。
- すべて `status=pending`（審査待ち）で入る。審査画面か Django admin で
  医学的な確認をして公開するまで、学習者の演習には出ない。
- 同梱データを直したら作り直す:
  `python scripts/build_question_import_sql.py import_cbt_basic_2026 cbt_batch_basic_2026.json`

## 公開中の国試を直す（kokushi_fix_2026_09*.sql）

国試PDFの字を字形で決めるようにして第114〜119回を取り込み直したところ、
公開中の設問に化けが見つかった（`scripts/build_kokushi_fix_sql.py` の冒頭に
内訳）。括弧が別の記号になったもの（「糖:−<」は「糖（−）」）、連問の症例文の
続きが前の設問の選択肢に付いていたもの、以前の手直しが推測で誤っていたもの。

| ファイル | 中身 |
|---|---|
| `kokushi_fix_2026_09.sql` | 公開中の33問の本文・選択肢・解説を直す（UPDATE） |
| `kokushi_fix_2026_09_add_01.sql` | 取り込み直して増えた147問を解説付きで入れる（INSERT、pending） |

- SQL Editor に1本ずつ貼る。順番は問わない。何度流しても結果は同じ。
- UPDATE は、本番の行が直す前の本文・選択肢のときだけ当てる（控えは
  `scripts/kokushi_fix/2026-09.json`）。審査で手を入れた行は上書きしない。
  最後の表で全問が「直した」か「すでに直っている」なら完了。「手で確認」が
  出た設問は、審査画面で本文を見比べて直す。
- INSERT は、同じ blueprint_code の国試の行がすでにあれば入れない。直した
  33問は本番にあるので入らず、増えた147問だけが審査待ちで入る。
- 公開の状態（status）は変えない。
- 同梱データを直したら作り直す: `python scripts/build_kokushi_fix_sql.py`
