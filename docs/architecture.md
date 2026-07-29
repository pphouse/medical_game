# アーキテクチャ

## 全体構成

```
┌────────────┐   Bearer JWT    ┌─────────────────────────┐
│ React SPA   │ ──────────────▶ │ Django + DRF (/api)      │
│ (Vite)      │                 │ 採点・習熟度・審査・集計   │
│ supabase-js │                 │ = 信頼が必要なロジック全部 │
└─────┬──────┘                 └───────────┬─────────────┘
      │ Auth / Realtime購読 /              │ テーブルオーナー接続
      │ claim_buzz RPC / Storage署名URL     │ (RLS の対象外)
      ▼                                    ▼
┌──────────────────────────────────────────────────────┐
│ Supabase: Postgres + Auth + Realtime + Storage        │
│   RLS: 既定は全拒否。例外は対戦テーブルの参加者 SELECT、 │
│   public_profiles ビュー、claim_buzz (SECURITY DEFINER) │
│   pg_cron → Edge Function (call-internal)              │
│     → Django /api/internal/*（X-Internal-Token）        │
└──────────────────────────────────────────────────────┘
```

設計原則: **クライアントは信用しない**。正誤判定・スコア・順位・審査状態の変更は
必ず Django（または SECURITY DEFINER な RPC）を通る。フロントが supabase-js で
直接触るのは「対戦テーブルの購読」「claim_buzz RPC」「学生証画像の署名付き
アップロード」のみ。

## 認証（フェーズ0）

- ユーザーは Supabase Auth（メール+パスワード / Magic Link）でログインし、
  取得した access token を `Authorization: Bearer` で API に添付する。
- `config/authentication.py` の `SupabaseJWTAuthentication` が HS256
  (`SUPABASE_JWT_SECRET`) で検証。`sub`/`aud`/`exp` を必須、`aud="authenticated"`。
- `accounts.Profile`（PK = `auth.users.id` の UUID）を初回アクセス時に自動作成し、
  `request.user` として返す。DRF の権限・スロットルはこの Profile で動く。
- `accounts.User`（AbstractUser）は **/admin/ のスタッフ専用**。アプリの FK は
  すべて Profile を指す。
- 401 はフロント（`src/api.js`）でセッション切れとして扱い、サインアウトして
  `/auth?reason=expired` へ誘導する（§5-9）。

## データモデルの要点

- `quiz.Question` — `status`（draft/pending/published/rejected）×
  `source`（seed/llm/user）× `visibility`（public/university_only）。
  `visible_to(profile)` が唯一の出題可否判定（一覧・解答・対戦・模試すべて経由）。
  正答率は解答10件未満なら非公開（`public_correct_rate`）。
- `quiz.AnswerHistory` — `context`（solo/battle/mock/review）付きの全解答ログ。
  習熟度（◎○△✕/未）は「◎と△を機械が付けない」既存設計を維持。
- `exams.RankingSnapshot` — ランキングはリクエスト時に集計せず、
  `aggregate_rankings` が書いたスナップショットを返すだけ（§5-6 の N+1 対策）。
- `battle.*` — ルーム/参加者/ラウンド/早押し。**BattleAnswer テーブルは無く**、
  正誤は AnswerHistory(context=battle) に記録。
- `accounts.StudentVerification` — 学生証審査。画像は Django を通らず
  Storage の private バケットへ署名付き URL で直接アップロード。

## ランキングの定義（フェーズ3, spec 3-2）

- 「解いた問題数」= `DISTINCT question_id`（同じ問題の解き直しは増えない）
- 「正答率」= **各問題の初回解答のみ**で計算し、**100問以上**解いた人だけが対象
- 対象 context は solo / review のみ（battle・mock は除外）
- 大学対抗 = 学生証認証済み & 10問以上解いたメンバーが **5人以上**いる大学のみ、
  メンバー平均で比較
- API はメールアドレスを一切返さない（表示名＋大学のみ）

## 対戦モード（フェーズ4）

- 6桁ルームコード。開始時に全ラウンドを一括生成し、1問ずつ公開。
- 早押しの順位付けはサーバー時刻のみ。Supabase 設定時は
  `claim_buzz` RPC（SECURITY DEFINER, `pg_advisory_xact_lock` +
  `clock_timestamp()`）、未設定時は Django の `select_for_update` フォールバック。
  クライアントのタイムスタンプは一切受け取らない。
- 回答権は早押し順。誤答で次の順位へ、全員誤答 or 30秒で正解公開→次ラウンド。
  進行はポーリング（1.5s）＋ Realtime 購読（設定時）で、
  切断者（30秒 heartbeat 無し）はラウンド進行から自動除外。
- `correct_choice_key` は**そのラウンドが閉じるまで**どの API にも載らない。

## 全国模試（フェーズ5）

- 開催期間内に開始→各問アップサート保存→提出。締切 = min(開始+制限時間, 終了時刻)。
- 採点は `grade_mock_exam`（締切後に一括実行）: 素点 → 順位 → パーセンタイル →
  偏差値（50+10z）→ 学内順位 → 分野別成績を確定し、AnswerHistory(context=mock,
  習熟度は変更しない) へコピー。採点前の結果 API は「採点中」を返し、
  設問・正解は模試終了までどのユーザーにも開示しない。

## 復習リマインド（フェーズ6）

- SM-2 の復習期限が5問以上たまったユーザーに Web Push（VAPID）。
- **オプトイン既定オフ**、時刻はユーザー設定（タイムゾーン対応）、1日1回まで。
  404/410 の購読は自動削除。`send_review_reminders` を毎時実行する想定。

## ユーザー問題作成と学生証認証（フェーズ7）

- 問題作成は学生証認証済みのみ（20問/日）。作成物は draft → 審査提出で pending →
  モデレーター承認で published。解答が付いた問題は解説の追記しか編集できない。
  公開中の本文を直すと自動で pending に戻る。通報3件で自動的に出題停止→再審査。
- `university_only` の所属大学は**サーバー側で作成者の大学に強制**
  （クライアント指定は無視）。
- 学生証画像: 申請 API が返す署名付き upload URL でフロントが直接 Storage に
  アップロード（Django は画像を受けない）。モデレーターの閲覧は5分署名 URL。
  却下時は即削除、承認後も90日で `cleanup_student_id_images` が削除。

## セキュリティ上の決定事項（変更しないこと）

1. `SUPABASE_SERVICE_ROLE_KEY` はバックエンド専用。CI がビルド成果物への混入を検査
2. ランキング等の API はメールアドレスを返さない
3. `correct_choice_key` / `explanation` は解答前に返さない（模試・対戦も同様）
4. 早押し順位はサーバー時刻のみで決定
5. CBT 出題基準の `objective_text` は生成プロンプト内部用途のみ（API 非公開、
   全文 CSV はコミットしない）
6. LLM 生成問題は人間の審査なしに公開されない（インポートは強制 pending）
7. 学生証画像は Django を経由しない・却下即削除・承認後90日で削除
8. 旧ハードコード SECRET_KEY は漏えい扱い（環境変数必須、本番はフォールバック無し）

## RLS / Supabase SQL

`supabase/migrations/` は Django のマイグレーションと**別系統**で、Supabase の
SQL Editor / CLI で適用する:

- `20260723000100_rls_lockdown.sql` — 既定全拒否（全テーブル RLS 有効 + 権限剥奪）。
  **Django の migrate で新テーブルを作るたびに再実行する**（冪等）
- `20260723000200_profiles_access.sql` — 自分の行のみの profiles アクセスと
  `public_profiles`（表示名等の公開ビュー）
- `20260723002000_claim_buzz.sql` — 早押し RPC（参加者チェック + advisory lock）
- `20260723002100_battle_rls.sql` — 対戦テーブルの参加者限定 SELECT + Realtime 公開
- `20260723001000_cron_schedules.sql` — pg_cron から Edge Function
  `call-internal` 経由で Django の集計/採点/リマインドを叩くテンプレート

## テスト戦略

- backend: pytest-django 69件。実 SQL を試験するため Postgres 必須
  （DISTINCT ON、advisory lock の並行性、`claim_buzz` の RPC 本体を
  `auth.uid()` スタブ付きでテスト DB に適用して4スレッド競争など）。
- frontend: vitest + Testing Library（ランキング表示、対戦の待機→出題→結果の遷移、
  早押し/回答権/待機の各状態）。
- CI: `.github/workflows/ci.yml`（backend: ruff/migrations check/pytest、
  frontend: oxlint/vitest/build/service-role 混入チェック）。
