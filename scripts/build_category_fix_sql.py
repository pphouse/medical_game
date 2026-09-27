#!/usr/bin/env python3
"""本番の分野名を、試験種別ごとの正規の科目名に揃える SQL を書き出す。

演習画面の科目一覧は分野名の DISTINCT なので、正規名でない名前が残って
いると同じ科目が2行に分かれて出る（国試で「放射線」と「放射線科」、CBT で
「麻酔」と「救急・中毒・麻酔」、「中毒・環境異常症」と「救急・中毒・麻酔」）。
科目立てを作り直す前の分野名が、本番の行にそのまま残っていたのが原因。

**正規名でない行だけ**を直す。正規名の行には触らないので、管理画面で
意図して付け直した分野は変わらない。移し先は同梱データ（CI で検査済み）の
科目で、設問は次の鍵で突き合わせる:

* 国試 … blueprint_code（"114-A-1"。設問ごとに一意）
* CBT  … 選択肢の並びの md5（CBT の中で一意）。取り込み後に選択肢を
          直した行のために、本文の md5 でも引く
* seed_demo の見本15問 … 本文の md5

その前に、四連問（question_set に属するタイプQの設問）を単問にほどく。
演習画面は設問を科目の一覧に1問ずつ並べ、どれからでも開ける作りなので、
4問を順に解かせることができず、「四連問 2/4」の印だけが付いた単問に
なっていた。症例文を設問の頭に付け（国試の連問をほどいたときと同じ
「症例文＋改行＋設問」）、セットから外す。同梱データも同じ形にしてある。

どれにも当たらなかった行は最後の表に出る（0行なら完了）。

使い方:
    python scripts/build_category_fix_sql.py
"""

import glob
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from quiz.categories import (  # noqa: E402
    CATEGORIES_BY_EXAM,
    CBT,
    KOKUSHI,
    MAJOR_CATEGORIES_BY_EXAM,
    normalize,
)

DATA_GLOB = os.path.join(ROOT, "backend/quiz/management/commands/data/*.json")
OUT = os.path.join(ROOT, "scripts/sql/fix_categories.sql")


def q(s):
    return "'" + s.replace("'", "''") + "'"


def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def fingerprint(choices):
    # SQL 側: string_agg(e->>'key' || ':' || (e->>'text'), '|' ORDER BY ord)
    return "|".join(f"{c['id']}:{c['text']}" for c in choices)


def load_seed_samples():
    """seed_demo の見本。本番に CBT 10問・国試 5問が入っている。"""
    import types

    # Django を起動せずに SAMPLE_QUESTIONS だけ読む。
    for mod in ("django", "django.core", "django.core.management",
                "django.core.management.base", "accounts", "accounts.models",
                "quiz.models"):
        sys.modules.setdefault(mod, types.ModuleType(mod))
    sys.modules["django.core.management.base"].BaseCommand = object
    sys.modules["accounts.models"].University = None
    sys.modules["quiz.models"].Question = None
    path = os.path.join(ROOT, "backend/quiz/management/commands/seed_demo.py")
    src = open(path, encoding="utf-8").read()
    ns = {}
    exec(compile(src.split("\nclass Command")[0], path, "exec"), ns)
    return ns["SAMPLE_QUESTIONS"]


def main():
    kokushi, cbt_fp, cbt_text = {}, {}, {}
    for path in sorted(glob.glob(DATA_GLOB)):
        if ".report." in path:
            continue
        for item in json.load(open(path, encoding="utf-8"))["questions"]:
            exam, cat = item["exam_type"], item["category"]
            assert cat in CATEGORIES_BY_EXAM[exam], (item.get("id"), cat)
            if exam == KOKUSHI:
                code = item["blueprint_code"]
                assert code not in kokushi, f"blueprint_code が重複: {code}"
                kokushi[code] = cat
            else:
                h = md5(fingerprint(item["choices"]))
                assert h not in cbt_fp, f"CBT の選択肢の指紋が重複: {item.get('id')}"
                cbt_fp[h] = cat
                t = md5(item["question_text"])
                assert t not in cbt_text, f"CBT の本文が重複: {item.get('id')}"
                cbt_text[t] = cat
        # 本物の4連問（question_sets）の各設問。分野はセット単位で持っている。
        for qs in json.load(open(path, encoding="utf-8")).get("question_sets", []):
            exam = qs.get("exam_type", CBT)
            assert exam == CBT, "国試の連問は question_sets では持っていない"
            cat = qs["category"]
            assert cat in CATEGORIES_BY_EXAM[exam], (qs.get("id"), cat)
            for step in qs["steps"]:
                h = md5(fingerprint(step["choices"]))
                assert h not in cbt_fp, f"4連問の選択肢の指紋が重複: {qs.get('id')}"
                cbt_fp[h] = cat
                t = md5(step["question_text"])
                assert t not in cbt_text, f"4連問の本文が重複: {qs.get('id')}"
                cbt_text[t] = cat

    seeds = []
    for s in load_seed_samples():
        exam = s["exam_type"]
        cat = normalize(s["category"], s["question_text"], exam_type=exam)
        assert cat in CATEGORIES_BY_EXAM[exam]
        seeds.append((exam, md5(s["question_text"]), cat))

    def canon(exam):
        return ", ".join(q(n) for n in CATEGORIES_BY_EXAM[exam])

    def values(rows):
        return ",\n".join(f"    ({', '.join(q(x) for x in r)})" for r in rows)

    choice_fp_sql = (
        "(SELECT md5(string_agg(e->>'key' || ':' || (e->>'text'), '|' ORDER BY ord))\n"
        "         FROM jsonb_array_elements(q.choices::jsonb) WITH ORDINALITY AS t(e, ord))"
    )

    # 演習画面の並び（category_sort_key と同じ）: メジャー科 → 残りの科目 →
    # 正規名でないもの（名前の順）。
    order_rows = []
    for exam in (CBT, KOKUSHI):
        for i, name in enumerate(CATEGORIES_BY_EXAM[exam]):
            group = 0 if name in MAJOR_CATEGORIES_BY_EXAM[exam] else 1
            order_rows.append((exam, name, str(group), str(i)))

    sql = f"""-- 本番の分野名を、試験種別ごとの正規の科目名に揃える。何度流しても結果は同じ。
-- scripts/build_category_fix_sql.py で生成（手で直さないこと）。
--
-- 演習画面の科目一覧は分野名の DISTINCT なので、正規名でない名前が残って
-- いると同じ科目が2行に分かれて出る。国試で「放射線」と「放射線科」、CBT で
-- 「麻酔」と「救急・中毒・麻酔」が並んでいたのはこれ。あわせて、CBT の
-- 「多選択肢・4連問」（4連問ではない小児の症例問題38問が入っていた）を
-- 科目から外し、各科へ振り分ける。
--
-- **正規名でない行だけ**を直す。正規名の行には触らない。
-- 移し先は同梱データの科目。最後に1つの表を出す（SQL Editor は最後の
-- SELECT しか表示しないため）。その表をそのまま貼ってほしい。

BEGIN;

-- (0) 四連問を単問にほどく。演習画面では4問を順に解かせられず、印だけの
-- 四連問になっていた。症例文を設問の頭に付けてセットから外す。すでに
-- 症例文で始まっている設問には付け足さない（二重にしない）。
CREATE TEMP TABLE _series ON COMMIT DROP AS
SELECT id, exam_type FROM quiz_question WHERE question_set_id IS NOT NULL;

UPDATE quiz_question AS q SET
    question_text = CASE
        WHEN left(q.question_text, char_length(s.case_stem)) = s.case_stem
            THEN q.question_text
        ELSE s.case_stem || E'\\n' || q.question_text
    END,
    question_type = 'M',
    question_set_id = NULL,
    set_order = NULL
FROM quiz_questionset AS s
WHERE q.question_set_id = s.id;

-- 直す前の分野名を控えておく（最後の表で「何を何へ移したか」を出すため）。
CREATE TEMP TABLE _before ON COMMIT DROP AS
SELECT id, exam_type, category FROM quiz_question
WHERE (exam_type = 'KOKUSHI' AND category NOT IN ({canon(KOKUSHI)}))
   OR (exam_type = 'CBT' AND category NOT IN ({canon(CBT)}));

-- (1) 国試: blueprint_code で突き合わせる。
UPDATE quiz_question AS q SET category = v.category
FROM (VALUES
{values(sorted(kokushi.items()))}
) AS v(blueprint_code, category)
WHERE q.exam_type = 'KOKUSHI' AND q.blueprint_code = v.blueprint_code
  AND q.id IN (SELECT id FROM _before);

-- (2a) CBT: 選択肢の並びの md5 で突き合わせる。
UPDATE quiz_question AS q SET category = v.category
FROM (VALUES
{values(sorted(cbt_fp.items()))}
) AS v(h, category)
WHERE q.exam_type = 'CBT' AND q.id IN (SELECT id FROM _before)
  AND {choice_fp_sql} = v.h;

-- (2b) CBT: 取り込み後に選択肢を直した行のために、本文の md5 でも引く。
UPDATE quiz_question AS q SET category = v.category
FROM (VALUES
{values(sorted(cbt_text.items()))}
) AS v(h, category)
WHERE q.exam_type = 'CBT' AND q.id IN (SELECT id FROM _before)
  AND q.category NOT IN ({canon(CBT)})
  AND md5(q.question_text) = v.h;

-- (3) seed_demo の見本（本文の md5）。
UPDATE quiz_question AS q SET category = v.category
FROM (VALUES
{values(seeds)}
) AS v(exam_type, h, category)
WHERE q.exam_type = v.exam_type AND q.id IN (SELECT id FROM _before)
  AND md5(q.question_text) = v.h;

-- 結果。4つの区分を1つの表にまとめる。
--   0.単問にした  … 四連問からほどいた設問の数
--   1.移した      … 何を何へ移したか（件数）
--   2.残った      … 正規名でないまま残った分野。0行なら完了
--   3.演習の一覧  … 演習画面に出る並び（公開中の設問）。記号は画面と同じ
WITH moved AS (
    SELECT b.exam_type, b.category AS before, q.category AS after, count(*) AS n
    FROM _before AS b JOIN quiz_question AS q ON q.id = b.id
    WHERE q.category <> b.category
    GROUP BY 1, 2, 3
),
leftover AS (
    SELECT exam_type, category, count(*) AS n FROM quiz_question
    WHERE (exam_type = 'KOKUSHI' AND category NOT IN ({canon(KOKUSHI)}))
       OR (exam_type = 'CBT' AND category NOT IN ({canon(CBT)}))
    GROUP BY 1, 2
),
canon_order AS (
    SELECT * FROM (VALUES
{values(order_rows)}
    ) AS v(exam_type, category, grp, pos)
),
listing AS (
    SELECT q.exam_type, q.category, count(*) AS n,
           coalesce(o.grp::int, 2) AS grp, coalesce(o.pos::int, 999) AS pos
    FROM quiz_question AS q
    LEFT JOIN canon_order AS o ON o.exam_type = q.exam_type AND o.category = q.category
    WHERE q.status = 'published' AND q.visibility = 'public'
    GROUP BY 1, 2, 4, 5
)
SELECT 区分, 試験, 記号, 分野, 問題数 FROM (
    SELECT '0.単問にした' AS 区分, exam_type AS 試験, '' AS 記号,
           '四連問の設問' AS 分野, count(*) AS 問題数, 0 AS k, 0 AS r
    FROM _series GROUP BY exam_type
    UNION ALL
    SELECT '1.移した', exam_type, '', before || ' → ' || after, n, 1, 0
    FROM moved
    UNION ALL
    SELECT '2.残った', exam_type, '', category, n, 2, 0 FROM leftover
    UNION ALL
    SELECT '3.演習の一覧', exam_type,
           chr(64 + row_number() OVER (PARTITION BY exam_type
                                       ORDER BY grp, pos, category COLLATE "C")::int),
           category || CASE WHEN grp = 2 THEN '（正規名でない）' ELSE '' END, n,
           3, row_number() OVER (PARTITION BY exam_type ORDER BY grp, pos, category COLLATE "C")
    FROM listing
) AS report
ORDER BY k, 試験, r, 分野;

COMMIT;
"""
    open(OUT, "w", encoding="utf-8").write(sql)
    print(f"{OUT}: 国試 {len(kokushi)} / CBT 指紋 {len(cbt_fp)} / CBT 本文 {len(cbt_text)} / 見本 {len(seeds)}"
          f" / {len(sql.encode()) // 1024} KB")


if __name__ == "__main__":
    main()
