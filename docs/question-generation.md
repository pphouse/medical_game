# LLM 問題生成パイプライン（フェーズ2）

CBT 出題基準（医学教育モデル・コア・カリキュラム準拠、CATO 公表 PDF）に沿って
Claude で問題の**下書き**を量産し、機械検証を通ったものだけを Django に
`status=pending` で取り込み、**必ず人間（モデレーター）が審査してから**公開する。

```
CATO PDF ──▶ scripts/extract_blueprint.py ──▶ data/cbt_blueprint.csv（コミットしない）
                                              │  manage.py import_blueprint
                                              ▼
                     scripts/generate_questions.py（ANTHROPIC_API_KEY 必須）
                                              │  data/generated/batch_*.json
                                              ▼
                     scripts/validate_questions.py（機械検証, 失敗で exit 1）
                                              │
                                              ▼
                     manage.py import_questions <json>   ← 強制 status=pending
                                              │
                                              ▼
                     モデレーター審査 API（/api/quiz/review/...）で approve
                                              ▼
                                          published（出題対象）
```

## 1. 出題基準の抽出 — `extract_blueprint.py`

```bash
python scripts/extract_blueprint.py path/to/cbt_kijun.pdf -o data/cbt_blueprint.csv
```

- 出力列: `code, section, area, area_title, subsection_title, objective_text,
  depth, class_group, disease_names`（実 PDF で 1404 行を確認済み）。
- コード単独行＋2行折返しのレイアウトに対応。NFKC 正規化は**しない**
  （①→1 に潰れて丸数字の枝番が壊れるため）。
- **著作権上の扱い**: `objective_text` を含む全文 CSV はリポジトリに
  コミットしない（.gitignore 済み）。コミットしてよいのは列構成を示す
  `data/cbt_blueprint.sample.csv` のみ。DB に取り込んだ場合も
  `objective_text` は生成プロンプト内部用途に限り、API には一切載せない。

DB への取り込み（模試の分野比率編成と審査画面の分野表示に使う）:

```bash
python manage.py import_blueprint data/cbt_blueprint.csv
```

## 2a. 直接執筆 — `author_core_batch.py`（API を使わない同梱バッチ）

API を呼ばずに問題を用意する経路。`scripts/author_core_batch.py` に問題本文を
インラインで持ち、`backend/quiz/management/commands/data/cbt_batch_core_2026.json`
を生成する。同梱の初期問題バンク（10分野の単問50問＋四連問2セット＝58問）は
この方法で作成している。正解キーは明示的に配置して検証器の数値ゲート
（A〜E各15〜25%、正解＝最長 40%未満）を満たすようにしてある。

```bash
python scripts/author_core_batch.py     # data/cbt_batch_core_2026.json を再生成
python scripts/validate_questions.py --file backend/quiz/management/commands/data/cbt_batch_core_2026.json
```

問題を増やす・直すときは `author_core_batch.py` の `M`（単問）/ `SETS`（四連問）/
`PEARLS_*`（解説に付す臨床のポイント）を編集して再生成し、検証器を通す。
このバッチは `tests/test_questions.py::TestBundledCoreBatch` が CI で検証し、
`import_questions` では他の生成物と同様に **status=pending** で取り込まれる
（デモ表示のみ `seed_demo --with-batch` が published として投入する）。

## 2b. 生成 — `generate_questions.py`（LLM API を使う場合）

```bash
export ANTHROPIC_API_KEY=...
python scripts/generate_questions.py \
  --blueprint data/cbt_blueprint.csv \
  --area D-5 --type M --per-code 2 \
  -o data/generated/batch_d5_m.json
```

- モデルは Claude（既定 `claude-opus-4-8`）、adaptive thinking + streaming。
- 出題基準の各学修目標（code）ごとに 1〜4問を生成。プロンプトは
  `scripts/prompts/question_m.md`（単問）/ `question_q.md`（四連問）。
- `--type Q` は症例文 + 4連問（`question_sets`）を出力する。
- 出力は `schemas/question_batch.schema.json` に従う JSON バッチ。
- 生成物はコミットしない（`data/generated/` は .gitignore 済み）。

## 3. 機械検証 — `validate_questions.py`

```bash
python scripts/validate_questions.py data/generated/batch_d5_m.json           # 単体
python scripts/validate_questions.py data/generated/*.json --check-db         # DB重複も見る
```

fail（exit 1, 取り込み不可）:

- JSON Schema 違反（5択 A–E、正解キー不在など構造エラー）
- 本文/解説の長さ逸脱（設問 40–600 / 解説 80–600 字）
- 禁止パターン（「上記のいずれでもない」等の指示書指定）
- バッチ内・既存バッチとの正規化ハッシュ重複

warn（取り込み可・審査で注意）:

- 最長選択肢＝正解の比率が 40% 超（正解が推測できる悪癖）
- 正解キー A–E の偏り（各 15–25% を外れる）
- `--check-db`: pg_trgm similarity ≥ 0.75 の既存類似問題

参考: 同梱デモバッチ（seed 由来）はこの検証器だと「正解キー100% A」で
警告される。実運用の生成では検証を通してから取り込むこと。

## 4. 取り込み — `manage.py import_questions`

```bash
python manage.py import_questions data/generated/batch_d5_m.json
```

- **どんな入力でも `status=pending` / `source=llm` を強制**する。
  公開するには審査 API（モデレーター）で approve するしかない。
- 選択肢の `{"id", "text"}` 形式は DB 正である `{"key", "text"}` へ変換（§5-10）。
- `distractor_rationale` は解説末尾に畳み込む。
- 四連問（`question_sets`）は QuestionSet + type=Q の4行として取り込み、
  審査は4問セットで一括 approve/reject。

## 5. 審査 → 公開

- モデレーター（`Profile.role = moderator/admin`）が
  `/api/quiz/review/questions/` の一覧から approve / reject。
  approve で `reviewed_by/reviewed_at` が記録され `published` になる。
- 公開後も通報が3件たまると自動で `pending` に戻り出題から外れる。

## 運用メモ

- 生成コストの目安を残すため、generate は 1 バッチ = 1 area を推奨
  （`--area D-5 --per-code 2` ≒ 数十問）。
- 「Q セット各分野 50 問」といった量産は `ANTHROPIC_API_KEY` と人手審査の
  体制が必要なため、リポジトリにはパイプラインのみを含める（生成済み問題の
  同梱はデモ用 seed のみ）。
