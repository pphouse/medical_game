#!/usr/bin/env python3
"""quiz/categories.py の分類規則から、本番DB用の UPDATE 文を生成する。

`manage.py reclassify_categories` と同じ結果になる SQL を出す。DBへ直に
接続できない環境（Vercel/Supabase のポートが塞がれている場合など）から、
SQL エディタ経由で分野名を移行するために使う。

    python scripts/gen_reclassify_sql.py > /tmp/reclassify.sql

分類は quiz.categories.classify と同じ規則にする。
「一致したキーワードの種類数が最多の分野を採り、同数なら RULES に先に
書いた分野を優先する」を、SQL 側では count(DISTINCT kw) と rule 順の
タイブレークで表す。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from quiz.categories import (  # noqa: E402
    CANONICAL_CATEGORIES,
    DEFAULT_CATEGORY,
    LEGACY_EXACT,
    OPEN_RECLASSIFY,
    RULES,
    SPLIT_SOURCES,
)


def q(text: str) -> str:
    """SQL のリテラルにする。"""
    return "'" + text.replace("'", "''") + "'"


def values(rows: list[tuple], indent: str = "    ") -> str:
    return ",\n".join(indent + "(" + ", ".join(rows_i) + ")" for rows_i in rows)


def main() -> int:
    rule_rows = []
    for order, (category, keywords) in enumerate(RULES):
        for keyword in dict.fromkeys(keywords):  # 重複キーワードは1回だけ数える
            rule_rows.append((q(category), str(order), q(keyword)))

    allowed_rows = [
        (q(src), q(cat)) for src, (cats, _fb) in SPLIT_SOURCES.items() for cat in cats
    ]
    fallback_rows = [(q(src), q(fb)) for src, (_cats, fb) in SPLIT_SOURCES.items()]
    legacy_rows = [(q(old), q(new)) for old, new in LEGACY_EXACT.items()]

    canonical = ", ".join(q(c) for c in CANONICAL_CATEGORIES)
    open_re = ", ".join(q(c) for c in sorted(OPEN_RECLASSIFY))
    split_src = ", ".join(q(c) for c in SPLIT_SOURCES)

    print(f"""-- 分野名を正規の分野立てに移行する（manage.py reclassify_categories と同じ結果）
-- scripts/gen_reclassify_sql.py が quiz/categories.py から生成したもの。手で編集しない。
--
-- 判定に使う本文は設問文・トピック・連問の症例文・選択肢を連結したもの。
-- reclassify_categories.question_text_for_classification と同じ。
BEGIN;

WITH rules(cat, ord, kw) AS (VALUES
{values(rule_rows)}
),
allowed(src, cat) AS (VALUES
{values(allowed_rows)}
),
fallback(src, cat) AS (VALUES
{values(fallback_rows)}
),
legacy(old, new) AS (VALUES
{values(legacy_rows)}
),
blob AS (
    SELECT
        q.id,
        q.category,
        concat_ws(E'\\n',
            q.question_text,
            q.topic,
            s.case_stem,
            (SELECT string_agg(c->>'text', E'\\n')
               FROM jsonb_array_elements(q.choices) AS c
              WHERE jsonb_typeof(q.choices) = 'array')
        ) AS t
    FROM quiz_question q
    LEFT JOIN quiz_questionset s ON s.id = q.question_set_id
),
scored AS (
    SELECT b.id, r.cat, min(r.ord) AS ord, count(DISTINCT r.kw) AS hits
    FROM blob b
    JOIN rules r ON strpos(b.t, r.kw) > 0
    GROUP BY b.id, r.cat
),
best_any AS (
    SELECT DISTINCT ON (id) id, cat
    FROM scored ORDER BY id, hits DESC, ord ASC
),
best_split AS (
    SELECT DISTINCT ON (s.id, a.src) s.id, a.src, s.cat
    FROM scored s JOIN allowed a ON a.cat = s.cat
    ORDER BY s.id, a.src, s.hits DESC, s.ord ASC
),
target AS (
    SELECT
        b.id,
        b.category AS old_category,
        CASE
            WHEN b.category IN ({canonical}) THEN b.category
            WHEN b.category IN ({split_src}) THEN coalesce(bs.cat, fb.cat)
            WHEN b.category IN ({open_re}) THEN coalesce(ba.cat, {q(DEFAULT_CATEGORY)})
            WHEN le.new IS NOT NULL THEN le.new
            ELSE coalesce(ba.cat, {q(DEFAULT_CATEGORY)})
        END AS new_category
    FROM blob b
    LEFT JOIN best_any   ba ON ba.id = b.id
    LEFT JOIN best_split bs ON bs.id = b.id AND bs.src = b.category
    LEFT JOIN fallback   fb ON fb.src = b.category
    LEFT JOIN legacy     le ON le.old = b.category
)
UPDATE quiz_question AS qq
   SET category = t.new_category
  FROM target t
 WHERE qq.id = t.id
   AND qq.category IS DISTINCT FROM t.new_category;

-- 移行後の内訳。正規の分野立て以外が残っていないか確認する。
SELECT category, count(*) AS n
  FROM quiz_question
 GROUP BY category
 ORDER BY n DESC;

COMMIT;
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
