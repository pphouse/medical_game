#!/usr/bin/env python3
"""未適用のデータマイグレーションを、Supabase の SQL エディタで流せる形にする。

    python3 backend/scripts/gen_supabase_migration_sql.py

`backend/scripts/sql/apply_pending_migrations.sql` を書き出す。中身は
quiz/0008〜0019・exams/0007〜0010 と `manage.py seed_editorial_questions`
と同じ結果になるように書いてある。

`manage.py migrate` を流せるならそちらが正。これは本番DBへ直接つなげない
ときの逃げ道で、何度流しても同じ結果になるように書いてある（どのマイグ
レーションまで当たっているか分からなくても流せるようにするため）。

設問の INSERT だけは同梱バッチ（data/*.json）から起こすので、このスクリプト
で生成する。それ以外は下のテンプレートに手で書いてある。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "quiz/management/commands/data"
OUT = ROOT / "scripts/sql/apply_pending_migrations.sql"

REVIEWED_BATCHES = (
    "cbt_batch_radiology_2026.json",
    "kokushi_batch_anesthesia_radiology_2026.json",
)

# quiz/0018 と同じ。設問の最後の一文に出たら主題がその領域だと言える語。
ASKED_RADIOLOGY = [
    "放射線", "被曝", "被ばく", "線量", "核医学", "シンチグラ",
    "照射", "画像下治療", "IVR",
]
ASKED_ANESTHESIA = [
    "麻酔", "気管挿管", "筋弛緩", "悪性高熱", "硬膜外",
    "脊髄くも膜下", "気道確保の手技", "鎮静",
]
ASKED_EXCEPTIONS = ["母子健康手帳", "母子保健法", "検疫法", "社会保障", "医療費"]

APPLIED = [
    ("quiz", "0008_strip_explanation_boilerplate"),
    ("quiz", "0009_question_choice_explanations"),
    ("quiz", "0010_backfill_choice_explanations"),
    ("quiz", "0011_merge_toxicology_into_emergency"),
    ("quiz", "0012_tumor_marker_choices_abbreviation_only"),
    ("quiz", "0013_merge_emergency_family"),
    ("quiz", "0014_reclassify_radiology_questions"),
    ("quiz", "0015_merge_urology_into_kidney"),
    ("quiz", "0016_consolidate_small_subjects"),
    ("quiz", "0017_split_kidney_and_urology"),
    ("quiz", "0018_unpack_series_and_align_categories"),
    ("quiz", "0019_split_radiology_and_anesthesia"),
    ("quiz", "0020_strip_stray_column_separators"),
    ("quiz", "0021_question_report_reasons"),
    ("exams", "0007_monthly_kokushi_is_for_fifth_year_and_up"),
    ("exams", "0008_rename_cbt_once_title"),
    ("exams", "0009_alter_mockexam_kind_label"),
    ("exams", "0010_cbt_exam_yearly_window"),
]


def lit(value):
    """SQL の文字列リテラル。"""
    return "'" + str(value).replace("'", "''") + "'"


def json_lit(value):
    return lit(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def text_array(values):
    return "ARRAY[" + ", ".join(lit(v) for v in values) + "]"


def insert_statements():
    out = []
    for name in REVIEWED_BATCHES:
        payload = json.loads((DATA / name).read_text(encoding="utf-8"))
        for item in payload["questions"]:
            choices = [{"key": c["id"], "text": c["text"]} for c in item["choices"]]
            notes = {
                str(k).strip().upper(): str(v).strip()
                for k, v in (item.get("distractor_rationale") or {}).items()
                if str(v).strip()
            }
            out.append(
                "INSERT INTO quiz_question (\n"
                "    category, difficulty, exam_type, choices, correct_choice_key,\n"
                "    explanation, visibility, correct_rate, created_at, question_text,\n"
                "    topic, answer_count, blueprint_code, class_group, question_type,\n"
                "    source, status, choice_explanations)\n"
                f"SELECT {lit(item['category'])}, 2, {lit(item['exam_type'])}, {json_lit(choices)},\n"
                f"       {lit(item['correct_choice_id'])}, {lit(item['explanation'])}, 'public', 0, now(),\n"
                f"       {lit(item['question_text'])},\n"
                f"       {lit(item.get('disease', ''))}, 0, '', '', 'M', 'llm', 'published', {json_lit(notes)}\n"
                "WHERE NOT EXISTS (\n"
                f"    SELECT 1 FROM quiz_question WHERE question_text = {lit(item['question_text'])});"
            )
    return "\n\n".join(out)


TEMPLATE = """\
-- 未適用のデータマイグレーションを当てる（Supabase の SQL Editor 用）。
--
-- backend/scripts/gen_supabase_migration_sql.py が生成。手で直さないこと。
--
-- 使い方:
--   1. 先に scripts/sql/fix_categories.sql を流す（＝マイグレーション 0018。
--      四連問を単問にほどき、分野を同梱データへそろえる）。
--   2. そのあとでこの全文をコピーして SQL Editor に貼り、実行する。
--
--   * 何度流しても同じ結果になる（途中まで当たっていても流してよい）。
--   * 全体が1つのトランザクションなので、途中で失敗すれば何も残らない。
--   * `manage.py migrate` を流せるならそちらが正。これは本番DBへ直接
--     つなげないときの逃げ道。
--
-- 中身は quiz/0008・0009・0010・0012・0019・0020 と exams/0007〜0010、
-- `manage.py seed_editorial_questions` と同じ。分野の統合（0011〜0017）は
-- fix_categories.sql が面倒を見るので、ここには入れていない。

BEGIN;

-- ===========================================================================
-- quiz/0009  選択肢ごとの解説を入れる列
-- ===========================================================================
ALTER TABLE quiz_question
    ADD COLUMN IF NOT EXISTS choice_explanations jsonb NOT NULL DEFAULT '{{}}'::jsonb;

-- ===========================================================================
-- quiz/0021  問題の報告に、選んだ理由をすべて持たせる列
-- ===========================================================================
ALTER TABLE quiz_questionreport
    ADD COLUMN IF NOT EXISTS reasons jsonb NOT NULL DEFAULT '[]'::jsonb;

-- すでにある報告は、単一の reason をそのまま一覧にする。
UPDATE quiz_questionreport
   SET reasons = jsonb_build_array(reason)
 WHERE reasons = '[]'::jsonb AND reason <> '';

-- ===========================================================================
-- quiz/0008  解説から定型文（出典URL・整形の注記・編集部の注記）を落とす
-- ===========================================================================
DO $strip$
DECLARE
    r          record;
    line       text;
    cleaned    text;
    kept       text[];
    new_text   text;
BEGIN
    FOR r IN SELECT id, explanation FROM quiz_question WHERE explanation <> '' LOOP
        kept := ARRAY[]::text[];
        FOREACH line IN ARRAY regexp_split_to_array(r.explanation, E'\\n') LOOP
            -- 行の途中に紛れ込んだ断片を先に抜く
            line := regexp_replace(
                line,
                '[／/、,]?[[:space:]]*[（(]?設問文および選択肢[はをに][^）)]*表示形式[^）)]*[)）]?',
                '', 'g');
            line := regexp_replace(line, '[※*]?[[:space:]]*[^。]*アプリ編集部[^。]*。?', '', 'g');
            line := regexp_replace(line, '[※*]?[[:space:]]*[^。]*過去問には解説は含まれ[^。]*。?', '', 'g');
            -- 出典の行に同居しているURLだけを落とす（本文中の参考リンクは残す）
            IF position('出典' in line) > 0 THEN
                line := regexp_replace(line, '[[:space:]]*[（(\\[]?https?://[^[:space:]]+[)）\\]]?', '', 'g');
            END IF;
            cleaned := btrim(line);
            -- 行まるごとが定型文なら落とす
            CONTINUE WHEN cleaned ~ '^[（(\\[]?[[:space:]]*https?://[^[:space:]]+[[:space:]]*[)）\\]]?$';
            CONTINUE WHEN cleaned ~ '^[（(※*]*[[:space:]]*設問文および選択肢.*表示形式.*$';
            CONTINUE WHEN cleaned ~ 'アプリ編集部' OR cleaned ~ '過去問には解説は含まれ';
            -- 断片を抜いた結果、区切り記号や括弧だけが残った行も落とす
            CONTINUE WHEN cleaned <> '' AND cleaned !~ '[^[:space:]／/、,（()）\\[\\]．.。-]';
            kept := array_append(kept, rtrim(line));
        END LOOP;
        new_text := btrim(regexp_replace(array_to_string(kept, E'\\n'), E'\\n{{3,}}', E'\\n\\n', 'g'));
        IF new_text IS DISTINCT FROM r.explanation THEN
            UPDATE quiz_question SET explanation = new_text WHERE id = r.id;
        END IF;
    END LOOP;
END
$strip$;

-- ===========================================================================
-- quiz/0010  本文末尾の【誤答選択肢の解説】を choice_explanations へ移す
-- ===========================================================================
DO $split$
DECLARE
    r         record;
    heading   text := '【誤答選択肢の解説】';
    pos       int;
    body      text;
    block     text;
    line      text;
    per       jsonb;
    cur       text;
    notes     text[];
    in_note   boolean;
    m         text[];
    tail      text;
BEGIN
    FOR r IN SELECT id, explanation FROM quiz_question
             WHERE position('【誤答選択肢の解説】' in explanation) > 0 LOOP
        pos      := position(heading in r.explanation);
        body     := substr(r.explanation, 1, pos - 1);
        block    := substr(r.explanation, pos + length(heading));
        per      := '{{}}'::jsonb;
        cur      := NULL;
        notes    := ARRAY[]::text[];
        in_note  := false;

        FOREACH line IN ARRAY regexp_split_to_array(block, E'\\n') LOOP
            -- 出典・注記に入ったら、以降はすべて本文側へ戻す
            IF in_note OR line ~ '^[[:space:]]*(※|\\*|出典|https?://)' THEN
                in_note  := true;
                notes    := array_append(notes, line);
                CONTINUE;
            END IF;
            -- 「A「選択肢の文言」: 解説」と「A: 解説」の2通りを受ける
            m := regexp_match(
                line,
                '^[[:space:]]*([A-F])[[:space:]]*(?:[「『].*[」』]|[(（].*[)）])[[:space:]]*[:：][[:space:]]*(.+)$');
            IF m IS NULL THEN
                m := regexp_match(line, '^[[:space:]]*([A-F])[[:space:]]*[:：)）.][[:space:]]*(.+)$');
            END IF;
            IF m IS NOT NULL THEN
                cur := m[1];
                per := per || jsonb_build_object(cur, btrim(m[2]));
            ELSIF cur IS NOT NULL AND btrim(line) <> '' THEN
                -- 折り返した続きの行は直前の選択肢にくっつける
                per := jsonb_set(per, ARRAY[cur], to_jsonb((per ->> cur) || ' ' || btrim(line)));
            END IF;
        END LOOP;

        CONTINUE WHEN per = '{{}}'::jsonb;

        body := btrim(body);
        tail := btrim(array_to_string(notes, E'\\n'));
        IF tail <> '' THEN
            body := CASE WHEN body = '' THEN tail ELSE body || E'\\n\\n' || tail END;
        END IF;
        UPDATE quiz_question
           SET explanation = body, choice_explanations = per
         WHERE id = r.id;
    END LOOP;
END
$split$;

-- ===========================================================================
-- quiz/0012  腫瘍マーカーの設問から和名を外し、略号だけにする
-- ===========================================================================
UPDATE quiz_question
   SET choices = (
           SELECT jsonb_agg(
                      CASE c ->> 'key'
                          WHEN 'A' THEN jsonb_set(c, '{{text}}', '"CEA"'::jsonb)
                          WHEN 'B' THEN jsonb_set(c, '{{text}}', '"AFP"'::jsonb)
                          WHEN 'C' THEN jsonb_set(c, '{{text}}', '"PSA"'::jsonb)
                          WHEN 'D' THEN jsonb_set(c, '{{text}}', '"CA15-3"'::jsonb)
                          WHEN 'E' THEN jsonb_set(c, '{{text}}', '"NSE"'::jsonb)
                          ELSE c
                      END
                      ORDER BY ord)
             FROM jsonb_array_elements(quiz_question.choices) WITH ORDINALITY AS t(c, ord)),
       explanation = replace(explanation, 'CEA（癌胎児性抗原）は', 'CEAは')
 WHERE question_text LIKE '68歳の男性。6か月前から便が細くなり%';

-- ===========================================================================
-- quiz/0019  放射線と麻酔を独立した科目に切り出す
-- ===========================================================================
-- 先に fix_categories.sql（＝マイグレーション 0018）を流しておくこと。
-- あちらが同梱データへ分野をそろえ直すので、順番が逆だとここで移した
-- 設問が元の分野へ戻される。
UPDATE quiz_question
   SET category = '救急・中毒'
 WHERE exam_type = 'KOKUSHI' AND category = '救急・中毒・麻酔';

UPDATE quiz_question
   SET category = '放射線'
 WHERE category = '放射線科';

UPDATE quiz_question
   SET category = '麻酔'
 WHERE exam_type = 'KOKUSHI' AND category IN ('麻酔', '麻酔科');

-- 設問の最後の「〜はどれか。」に放射線／麻酔の語が出るものだけを移す。
-- 画像や全身麻酔は各科の臨床問題にも普通に出てくるので、本文のどこかに
-- 語が在るだけでは動かさない。
DO $asked$
DECLARE
    r          record;
    asked      text;
    word       text;
    is_rad     boolean;
    is_ane     boolean;
    radiology  text[] := {asked_radiology};
    anesthesia text[] := {asked_anesthesia};
    skip_words text[] := {asked_exceptions};
BEGIN
    FOR r IN SELECT id, exam_type, category, question_text FROM quiz_question LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM unnest(skip_words) AS s(w) WHERE position(s.w in r.question_text) > 0);

        asked := coalesce((
            SELECT m[1]
              FROM regexp_matches(r.question_text, E'([^。\\n]*か。)', 'g') WITH ORDINALITY AS t(m, i)
             ORDER BY i DESC
             LIMIT 1), '');
        CONTINUE WHEN asked = '';

        is_rad := false;
        FOREACH word IN ARRAY radiology LOOP
            IF position(word in asked) > 0 THEN is_rad := true; END IF;
        END LOOP;
        IF is_rad THEN
            IF r.category <> '放射線' THEN
                UPDATE quiz_question SET category = '放射線' WHERE id = r.id;
            END IF;
            CONTINUE;
        END IF;

        CONTINUE WHEN r.exam_type <> 'KOKUSHI';

        is_ane := false;
        FOREACH word IN ARRAY anesthesia LOOP
            IF position(word in asked) > 0 THEN is_ane := true; END IF;
        END LOOP;
        IF is_ane AND r.category <> '麻酔' THEN
            UPDATE quiz_question SET category = '麻酔' WHERE id = r.id;
        END IF;
    END LOOP;
END
$asked$;

-- ===========================================================================
-- quiz/0020  語の途中に紛れ込んだ列区切り "—" を落とす
-- ===========================================================================
-- 「Bell麻痺— の症状で誤って— いるのはどれか。」のように、PDFの取り込みで
-- 字間の広い箇所へ差し込んだ区切りが語中に入っていた。前後に空白のある
-- "—" は組合せ問題の正しい列区切りなので触らない。
DO $sep$
DECLARE
    r        record;
    combo    boolean;
    new_text text;
    new_ch   jsonb;
BEGIN
    FOR r IN SELECT id, question_text, choices FROM quiz_question
             WHERE position('—' in question_text) > 0
                OR position('—' in choices::text) > 0 LOOP
        -- 組合せ問題の選択肢だけは、列の境目として区切りを残す
        combo := position('組合せ' in coalesce(r.question_text, '')) > 0;

        new_text := regexp_replace(
                        regexp_replace(
                            regexp_replace(coalesce(r.question_text, ''),
                                           '—[[:space:]]*([:：])', '\\1', 'g'),
                            '([^[:space:]])—[[:space:]]*', '\\1', 'g'),
                        '^—[[:space:]]*', '', '');

        new_ch := (
            SELECT jsonb_agg(
                       jsonb_set(c, '{{text}}', to_jsonb(
                           regexp_replace(
                               regexp_replace(
                                   regexp_replace(coalesce(c ->> 'text', ''),
                                                  '—[[:space:]]*([:：])', '\\1', 'g'),
                                   '([^[:space:]])—[[:space:]]*',
                                   CASE WHEN combo THEN '\\1 — ' ELSE '\\1' END, 'g'),
                               '^—[[:space:]]*', '', '')))
                       ORDER BY ord)
              FROM jsonb_array_elements(r.choices) WITH ORDINALITY AS t(c, ord));

        IF new_text IS DISTINCT FROM r.question_text
           OR new_ch IS DISTINCT FROM r.choices THEN
            UPDATE quiz_question
               SET question_text = new_text,
                   choices = coalesce(new_ch, r.choices)
             WHERE id = r.id;
        END IF;
    END LOOP;
END
$sep$;

-- ===========================================================================
-- seed_editorial_questions  放射線（CBT・国試）と麻酔（国試）の設問を足す
-- ===========================================================================
{inserts}

-- ===========================================================================
-- exams/0007  月次実力テストの国試版を5年生以上に限定する
-- ===========================================================================
UPDATE exams_mockexam
   SET target_grade_min = 5
 WHERE kind = 'monthly' AND exam_type = 'KOKUSHI' AND target_grade_min IS NULL;

-- ===========================================================================
-- exams/0008  CBT模試のタイトルから「（生涯1回）」を外す
-- ===========================================================================
UPDATE exams_mockexam
   SET title = 'CBT全国模試'
 WHERE kind = 'cbt_once' AND title = 'CBT全国模試（生涯1回）';

-- ===========================================================================
-- exams/0010  CBT模試の受験可能期間を 7月1日〜翌3月31日 にする
-- ===========================================================================
UPDATE exams_mockexam e
   SET start_at = make_timestamptz(w.fiscal_year, 7, 1, 0, 0, 0, 'Asia/Tokyo'),
       end_at   = make_timestamptz(w.fiscal_year + 1, 3, 31, 23, 59, 59, 'Asia/Tokyo')
  FROM (
        SELECT id,
               CASE WHEN EXTRACT(MONTH FROM start_at AT TIME ZONE 'Asia/Tokyo') >= 4
                    THEN EXTRACT(YEAR FROM start_at AT TIME ZONE 'Asia/Tokyo')::int
                    ELSE EXTRACT(YEAR FROM start_at AT TIME ZONE 'Asia/Tokyo')::int - 1
               END AS fiscal_year
          FROM exams_mockexam
         WHERE kind = 'cbt_once'
       ) w
 WHERE e.id = w.id;

-- ===========================================================================
-- django_migrations に「当てた」ことを記録する
-- ===========================================================================
-- これを入れておかないと、あとから `manage.py migrate` を流したときに
-- 同じ処理をもう一度走らせようとする（内容は冪等なので壊れはしないが、
-- 当たっているかどうかを見て分かるようにしておく）。
INSERT INTO django_migrations (app, name, applied)
SELECT v.app, v.name, now()
  FROM (VALUES
{applied}
       ) AS v(app, name)
 WHERE NOT EXISTS (
       SELECT 1 FROM django_migrations d WHERE d.app = v.app AND d.name = v.name);

COMMIT;
"""


def main():
    sql = TEMPLATE.format(
        asked_radiology=text_array(ASKED_RADIOLOGY),
        asked_anesthesia=text_array(ASKED_ANESTHESIA),
        asked_exceptions=text_array(ASKED_EXCEPTIONS),
        inserts=insert_statements(),
        applied=",\n".join(f"           ({lit(app)}, {lit(name)})" for app, name in APPLIED),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(sql, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT.parent)}  {len(sql.splitlines())}行")


if __name__ == "__main__":
    main()
