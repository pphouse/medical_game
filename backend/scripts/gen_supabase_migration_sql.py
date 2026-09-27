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

# quiz/0013 と同じ。取り込み時期でばらけた救急系の旧名。
# 「麻酔」はこの表に入れない。0018 のあとは国試の正規の科目名なので、
# 入れるともう一度流したときに救急へ吸われてしまう（CBTの「麻酔」だけは
# 別の UPDATE で寄せる）。同じ理由で 0015 の表からも「泌尿器」を外してある。
EMERGENCY_LEGACY = [
    "中毒", "中毒・環境", "中毒・環境異常症", "中毒・物理化学的因子",
    "救急", "救急系", "救急・中毒", "救急・集中治療", "麻酔科",
]

# quiz/0014 と同じ。放射線そのものを主題にした設問の語。
RADIOLOGY_SUBJECT_MARKERS = [
    "放射線被ばく", "放射線被曝", "被曝線量", "被ばく線量", "密封線源",
    "放射性物質", "定位放射線", "放射線治療で最も", "放射線療法で最も",
    "放射線宿酔",
]

# quiz/0016 と同じ。膠原病そのものを主題にした設問の語。
IMMUNOLOGY_MARKERS = [
    "関節リウマチの", "膠原病", "自己抗体と", "抗リン脂質抗体症候群",
    "好中球の構成成分に対する自己抗体", "ANCA関連", "Sjögren症候群",
    "シェーグレン症候群", "皮膚筋炎", "多発性筋炎", "全身性強皮症",
    "ベーチェット", "成人Still病", "リウマチ性多発筋痛症",
    "結節性多発動脈炎", "顕微鏡的多発血管炎", "巨細胞性動脈炎",
]

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

# quiz/categories.UROLOGY_KEYWORDS と同じ（0017 が使う）。
UROLOGY_KEYWORDS = [
    "前立腺", "膀胱", "尿管", "尿道", "精巣", "陰茎", "陰囊", "陰嚢", "精索",
    "尿路結石", "腎結石", "水腎症", "腎細胞癌", "腎盂", "尿路上皮",
    "排尿障害", "尿閉", "夜間頻尿", "過活動膀胱", "神経因性膀胱",
    "包茎", "停留精巣", "精巣捻転", "腎摘", "TUR",
]

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
    ("quiz", "0018_split_radiology_and_anesthesia"),
    ("quiz", "0019_strip_stray_column_separators"),
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


def in_list(values):
    return "(" + ", ".join(lit(v) for v in values) + ")"


def like_any(column, needles):
    return "(" + "\n       OR ".join(f"{column} LIKE {lit('%' + n + '%')}" for n in needles) + ")"


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
-- 使い方: 全文をコピーして SQL Editor に貼り、実行する。
--   * 何度流しても同じ結果になる（途中まで当たっていても流してよい）。
--   * 全体が1つのトランザクションなので、途中で失敗すれば何も残らない。
--   * `manage.py migrate` を流せるならそちらが正。これは本番DBへ直接
--     つなげないときの逃げ道。
--
-- 中身は quiz/0008〜0019・exams/0007〜0010 と
-- `manage.py seed_editorial_questions` と同じ。

BEGIN;

-- ===========================================================================
-- quiz/0009  選択肢ごとの解説を入れる列
-- ===========================================================================
ALTER TABLE quiz_question
    ADD COLUMN IF NOT EXISTS choice_explanations jsonb NOT NULL DEFAULT '{{}}'::jsonb;

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
-- quiz/0011, quiz/0013  救急・中毒・麻酔の旧科目名をまとめる
-- ===========================================================================
UPDATE quiz_question
   SET category = '救急・中毒・麻酔'
 WHERE category IN {emergency_legacy};

-- CBT には麻酔の科目が無いので、CBTの「麻酔」もここへ寄せる。国試の
-- 「麻酔」は 0018 で立てた正規の科目名なので触らない。
UPDATE quiz_question
   SET category = '救急・中毒・麻酔'
 WHERE exam_type = 'CBT' AND category = '麻酔';

-- ===========================================================================
-- quiz/0014  放射線そのものを主題にした設問を集める（国試）
-- ===========================================================================
UPDATE quiz_question
   SET category = '放射線科'
 WHERE exam_type = 'KOKUSHI'
   AND category NOT IN ('放射線科', '放射線')
   AND {radiology_subject};

-- ===========================================================================
-- quiz/0015  被っていた「泌尿器科」を「腎・泌尿器」に寄せる
-- ===========================================================================
UPDATE quiz_question
   SET category = '腎・泌尿器'
 WHERE category IN ('泌尿器科', '泌尿器系');

-- ===========================================================================
-- quiz/0016  問題数の少ない科目を整理する（国試）
-- ===========================================================================
UPDATE quiz_question
   SET category = '免疫・膠原病'
 WHERE exam_type = 'KOKUSHI'
   AND category <> '免疫・膠原病'
   AND question_text NOT LIKE '%歳の%'
   AND {immunology};

UPDATE quiz_question
   SET category = '医学総論'
 WHERE exam_type = 'KOKUSHI'
   AND category IN ('放射線科', '必修問題');

-- ===========================================================================
-- quiz/0017  「腎・泌尿器」を「腎臓」と「泌尿器」に分ける
-- ===========================================================================
UPDATE quiz_question
   SET category = '泌尿器'
 WHERE category IN ('腎・泌尿器', '腎・尿路系')
   AND {urology};

UPDATE quiz_question
   SET category = '腎臓'
 WHERE category IN ('腎・泌尿器', '腎・尿路系');

-- ===========================================================================
-- quiz/0018  放射線と麻酔を独立した科目に切り出す
-- ===========================================================================
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
-- quiz/0019  語の途中に紛れ込んだ列区切り "—" を落とす
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
        emergency_legacy=in_list(EMERGENCY_LEGACY),
        radiology_subject=like_any("question_text", RADIOLOGY_SUBJECT_MARKERS),
        immunology=like_any("question_text", IMMUNOLOGY_MARKERS),
        urology=like_any("question_text", UROLOGY_KEYWORDS),
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
