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
    ADD COLUMN IF NOT EXISTS choice_explanations jsonb NOT NULL DEFAULT '{}'::jsonb;

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
        FOREACH line IN ARRAY regexp_split_to_array(r.explanation, E'\n') LOOP
            -- 行の途中に紛れ込んだ断片を先に抜く
            line := regexp_replace(
                line,
                '[／/、,]?[[:space:]]*[（(]?設問文および選択肢[はをに][^）)]*表示形式[^）)]*[)）]?',
                '', 'g');
            line := regexp_replace(line, '[※*]?[[:space:]]*[^。]*アプリ編集部[^。]*。?', '', 'g');
            line := regexp_replace(line, '[※*]?[[:space:]]*[^。]*過去問には解説は含まれ[^。]*。?', '', 'g');
            -- 出典の行に同居しているURLだけを落とす（本文中の参考リンクは残す）
            IF position('出典' in line) > 0 THEN
                line := regexp_replace(line, '[[:space:]]*[（(\[]?https?://[^[:space:]]+[)）\]]?', '', 'g');
            END IF;
            cleaned := btrim(line);
            -- 行まるごとが定型文なら落とす
            CONTINUE WHEN cleaned ~ '^[（(\[]?[[:space:]]*https?://[^[:space:]]+[[:space:]]*[)）\]]?$';
            CONTINUE WHEN cleaned ~ '^[（(※*]*[[:space:]]*設問文および選択肢.*表示形式.*$';
            CONTINUE WHEN cleaned ~ 'アプリ編集部' OR cleaned ~ '過去問には解説は含まれ';
            -- 断片を抜いた結果、区切り記号や括弧だけが残った行も落とす
            CONTINUE WHEN cleaned <> '' AND cleaned !~ '[^[:space:]／/、,（()）\[\]．.。-]';
            kept := array_append(kept, rtrim(line));
        END LOOP;
        new_text := btrim(regexp_replace(array_to_string(kept, E'\n'), E'\n{3,}', E'\n\n', 'g'));
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
        per      := '{}'::jsonb;
        cur      := NULL;
        notes    := ARRAY[]::text[];
        in_note  := false;

        FOREACH line IN ARRAY regexp_split_to_array(block, E'\n') LOOP
            -- 出典・注記に入ったら、以降はすべて本文側へ戻す
            IF in_note OR line ~ '^[[:space:]]*(※|\*|出典|https?://)' THEN
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

        CONTINUE WHEN per = '{}'::jsonb;

        body := btrim(body);
        tail := btrim(array_to_string(notes, E'\n'));
        IF tail <> '' THEN
            body := CASE WHEN body = '' THEN tail ELSE body || E'\n\n' || tail END;
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
                          WHEN 'A' THEN jsonb_set(c, '{text}', '"CEA"'::jsonb)
                          WHEN 'B' THEN jsonb_set(c, '{text}', '"AFP"'::jsonb)
                          WHEN 'C' THEN jsonb_set(c, '{text}', '"PSA"'::jsonb)
                          WHEN 'D' THEN jsonb_set(c, '{text}', '"CA15-3"'::jsonb)
                          WHEN 'E' THEN jsonb_set(c, '{text}', '"NSE"'::jsonb)
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
    radiology  text[] := ARRAY['放射線', '被曝', '被ばく', '線量', '核医学', 'シンチグラ', '照射', '画像下治療', 'IVR'];
    anesthesia text[] := ARRAY['麻酔', '気管挿管', '筋弛緩', '悪性高熱', '硬膜外', '脊髄くも膜下', '気道確保の手技', '鎮静'];
    skip_words text[] := ARRAY['母子健康手帳', '母子保健法', '検疫法', '社会保障', '医療費'];
BEGIN
    FOR r IN SELECT id, exam_type, category, question_text FROM quiz_question LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM unnest(skip_words) AS s(w) WHERE position(s.w in r.question_text) > 0);

        asked := coalesce((
            SELECT m[1]
              FROM regexp_matches(r.question_text, E'([^。\n]*か。)', 'g') WITH ORDINALITY AS t(m, i)
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
                                           '—[[:space:]]*([:：])', '\1', 'g'),
                            '([^[:space:]])—[[:space:]]*', '\1', 'g'),
                        '^—[[:space:]]*', '', '');

        new_ch := (
            SELECT jsonb_agg(
                       jsonb_set(c, '{text}', to_jsonb(
                           regexp_replace(
                               regexp_replace(
                                   regexp_replace(coalesce(c ->> 'text', ''),
                                                  '—[[:space:]]*([:：])', '\1', 'g'),
                                   '([^[:space:]])—[[:space:]]*',
                                   CASE WHEN combo THEN '\1 — ' ELSE '\1' END, 'g'),
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
INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "発癌"}, {"key": "B", "text": "白内障"}, {"key": "C", "text": "皮膚の潰瘍"}, {"key": "D", "text": "一時的不妊"}, {"key": "E", "text": "造血機能の低下"}]'::jsonb,
       'A', '確定的影響（組織反応）はしきい線量を超えると必ず起こり、線量が増えるほど重くなる。これに対して確率的影響はしきい線量が無く、線量が増えるほど起こる確率が高くなるもので、発癌と遺伝性影響の2つを指す。放射線防護は、確定的影響を起こさせないことと、確率的影響の発生確率を合理的に達成できる限り低く保つことの2つを目的にしている。', 'public', 0, now(),
       '放射線防護では、影響の現れ方によって確定的影響と確率的影響とを区別して考える。このうち、しきい線量が無いと考えられているのはどれか。',
       '放射線の生体影響', 0, '', '', 'M', 'llm', 'published', '{"B": "水晶体のしきい線量を超えて初めて起こる確定的影響である。", "C": "数Gy以上でしきい線量を超えたときに現れる確定的影響である。", "D": "精巣でおよそ0.15Gyというしきい線量が知られる確定的影響である。", "E": "骨髄のしきい線量を超えたときに起こる確定的影響である。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '放射線防護では、影響の現れ方によって確定的影響と確率的影響とを区別して考える。このうち、しきい線量が無いと考えられているのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "1年間で1mSvを超えない"}, {"key": "B", "text": "5年間で100mSvを超えず、かつ1年間で50mSvを超えない"}, {"key": "C", "text": "1か月で5mSvを超えない"}, {"key": "D", "text": "生涯で10mSvを超えない"}, {"key": "E", "text": "1回の作業で0.1mSvを超えない"}]'::jsonb,
       'B', '放射線業務従事者の実効線量限度は「5年間で100mSv、かつ1年間で50mSv」と定められている。5年という期間で平均しつつ、1年に偏って受けることも抑える仕組みである。これとは別に、眼の水晶体や皮膚には等価線量の限度があり、妊娠を申告した女性の従事者には出産までの腹部表面の等価線量など、さらに厳しい限度が定められている。', 'public', 0, now(),
       '放射線を扱う医療機関では、従事者の被ばくを線量計で測り、記録して管理している。放射線業務従事者の実効線量限度として正しいのはどれか。',
       '線量限度', 0, '', '', 'M', 'llm', 'published', '{"A": "公衆の線量限度であり、業務従事者の限度ではない。", "C": "1か月を単位とした実効線量限度は定められていない。", "D": "生涯を単位とした実効線量限度は定められていない。", "E": "作業ごとの実効線量限度は定められていない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '放射線を扱う医療機関では、従事者の被ばくを線量計で測り、記録して管理している。放射線業務従事者の実効線量限度として正しいのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "胸部単純エックス線撮影"}, {"key": "B", "text": "マンモグラフィ"}, {"key": "C", "text": "腹部超音波検査"}, {"key": "D", "text": "骨シンチグラフィ"}, {"key": "E", "text": "上部消化管エックス線造影"}]'::jsonb,
       'C', '超音波検査は音波を、MRIは磁場と電波を使うので電離放射線による被ばくが無い。被ばくの影響を受けやすい小児・妊婦・若年女性では、まずこの2つで目的を果たせないかを考える。一方、エックス線を使う検査や放射性医薬品を投与する核医学検査はいずれも被ばくを伴うので、検査の必要性を説明したうえで行う。', 'public', 0, now(),
       '画像検査を選ぶときは、得られる情報と被ばくとを天秤にかけて考える。次の検査のうち、電離放射線による被ばくを伴わないのはどれか。',
       '画像検査と被ばく', 0, '', '', 'M', 'llm', 'published', '{"A": "エックス線を用いるので被ばくを伴う。実効線量は0.1mSvに満たず、検査としては少ない部類である。", "B": "乳房にエックス線を照射する検査であり、被ばくを伴う。", "D": "放射性医薬品を体内に投与する検査であり、内部被ばくを伴う。", "E": "透視と撮影を繰り返すので、単純撮影より被ばくは多い。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '画像検査を選ぶときは、得られる情報と被ばくとを天秤にかけて考える。次の検査のうち、電離放射線による被ばくを伴わないのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "気管支喘息があっても副作用の危険は高まらない"}, {"key": "B", "text": "副作用は投与直後に限られ、数時間後に現れることはない"}, {"key": "C", "text": "ビグアナイド薬は造影剤の投与直後から再開してよい"}, {"key": "D", "text": "以前にヨード造影剤で重篤な副作用を起こした患者では、原則として使用を避ける"}, {"key": "E", "text": "腎機能が低下した患者ほど造影剤腎症は起こりにくい"}]'::jsonb,
       'D', '重篤な副作用の既往は最も強い危険因子で、原則として再投与を避ける。やむを得ず使う場合は必要性を十分に検討し、救急対応の準備をしたうえで行う。気管支喘息・アレルギー素因・腎機能の低下も危険因子で、いずれも造影の前に確認しておく項目である。副作用には即時型と遅発型があり、帰宅後の症状についても説明しておく。', 'public', 0, now(),
       '造影CTを予定した患者について、問診の結果をふまえて造影剤の使用の可否を検討している。ヨード造影剤の使用について正しいのはどれか。',
       'ヨード造影剤', 0, '', '', 'M', 'llm', 'published', '{"A": "気管支喘息は副作用の危険を高める。アレルギー素因も同様である。", "B": "投与から1時間以内の即時型のほかに、数時間から数日後に皮疹などで現れる遅発型がある。", "C": "乳酸アシドーシスを避けるため、造影剤の投与後48時間は休薬し、腎機能を確かめてから再開する。", "E": "腎機能の低下は造影剤腎症の最大の危険因子で、低下しているほど起こりやすい。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '造影CTを予定した患者について、問診の結果をふまえて造影剤の使用の可否を検討している。ヨード造影剤の使用について正しいのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "亜急性甲状腺炎"}, {"key": "B", "text": "無痛性甲状腺炎"}, {"key": "C", "text": "機能性結節〈Plummer病〉"}, {"key": "D", "text": "ヨードの過剰摂取による甲状腺機能低下症"}, {"key": "E", "text": "Basedow病"}]'::jsonb,
       'E', 'Basedow病では甲状腺刺激ホルモン受容体に対する自己抗体が甲状腺を持続的に刺激するため、ヨードの取り込みが亢進して甲状腺全体にびまん性の高集積を示す。甲状腺中毒症をきたす疾患のうち、破壊性甲状腺炎ではホルモンが漏れ出ているだけなので取り込みは低下し、機能性結節では結節だけに集積する。集積の分布が鑑別の決め手になる。', 'public', 0, now(),
       '甲状腺中毒症を呈する患者の鑑別のために甲状腺シンチグラフィを行った。甲状腺全体にびまん性の高集積を示すのはどれか。',
       '核医学（甲状腺）', 0, '', '', 'M', 'llm', 'published', '{"A": "破壊性甲状腺炎であり、蓄えられたホルモンが漏れ出るだけなので取り込みは低下する。", "B": "同じく破壊性甲状腺炎であり、取り込みは低下する。", "C": "結節だけに集積し、周囲の甲状腺の集積はむしろ抑制される。", "D": "ヨードが過剰にあると放射性ヨードの取り込みは希釈されて低下する。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '甲状腺中毒症を呈する患者の鑑別のために甲状腺シンチグラフィを行った。甲状腺全体にびまん性の高集積を示すのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "活動性の炎症・感染の病巣"}, {"key": "B", "text": "高分化型肝細胞癌"}, {"key": "C", "text": "粘液の産生が多い高分化型の腺癌"}, {"key": "D", "text": "前立腺癌"}, {"key": "E", "text": "腎細胞癌"}]'::jsonb,
       'A', 'FDGはブドウ糖と同じように細胞へ取り込まれるので、糖代謝が亢進していれば腫瘍でなくても集積する。活動性の炎症・感染の病巣、サルコイドーシスなどの肉芽腫、手術の創、寒冷時の褐色脂肪組織が代表的な偽陽性の原因である。逆に、糖代謝の低い腫瘍や細胞密度の低い腫瘍、排泄経路に重なる腫瘍は偽陰性になりやすい。', 'public', 0, now(),
       'FDG-PETは糖代謝の亢進を画像化する検査で、悪性腫瘍の検索に広く使われている。この検査で偽陽性となりやすいのはどれか。',
       '核医学（FDG-PET）', 0, '', '', 'M', 'llm', 'published', '{"B": "周囲の肝実質にもともと集積があるため差が付きにくく、偽陰性になりやすい。", "C": "細胞の密度が低いため集積に乏しく、偽陰性になりやすい。", "D": "糖代謝が低く集積に乏しいため、偽陰性になりやすい。", "E": "FDGが尿へ排泄されて腎に溜まるため見分けにくく、偽陰性になりやすい。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = 'FDG-PETは糖代謝の亢進を画像化する検査で、悪性腫瘍の検索に広く使われている。この検査で偽陽性となりやすいのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "腫瘍の再酸素化を防ぐため"}, {"key": "B", "text": "正常組織の回復を促し、有害事象を軽くするため"}, {"key": "C", "text": "治療にかかる期間を短くするため"}, {"key": "D", "text": "照射装置にかかる負担を減らすため"}, {"key": "E", "text": "腫瘍細胞の細胞周期を分裂期で止めたままにするため"}]'::jsonb,
       'B', '分割照射では1回の線量を小さくすることで、正常組織が照射の合間に損傷から回復できる。正常組織は腫瘍より回復が早いので、分割するほど腫瘍と正常組織の反応の差が広がる。あわせて、照射の合間に腫瘍の中心部が再酸素化して感受性が高まり、細胞周期の再分布も起こるため、腫瘍への効果はむしろ保たれる。', 'public', 0, now(),
       '根治を目指す放射線治療では、総線量を1回で与えず、何週かに分けて少しずつ照射するのが一般的である。このように分割して照射する主な理由はどれか。',
       '放射線治療（分割照射）', 0, '', '', 'M', 'llm', 'published', '{"A": "再酸素化は分割照射の利点であって、防ぐべきものではない。", "C": "分割すると治療期間はむしろ数週間に延びる。", "D": "装置の都合で決めているのではなく、正常組織と腫瘍の反応の違いに基づく。", "E": "周期を止めるのではなく、再分布によって感受性の高い時期に当てることをねらう。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '根治を目指す放射線治療では、総線量を1回で与えず、何週かに分けて少しずつ照射するのが一般的である。このように分割して照射する主な理由はどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "胃癌"}, {"key": "B", "text": "膵癌"}, {"key": "C", "text": "子宮頸癌"}, {"key": "D", "text": "大腸癌"}, {"key": "E", "text": "急性リンパ性白血病"}]'::jsonb,
       'C', '密封小線源治療では線源を病巣のすぐ近くに置くため、距離の2乗に反比例して線量が落ち、周囲の正常組織を守りながら病巣に高い線量を集められる。子宮頸癌では腔内照射が根治的治療の柱で、外部照射と組み合わせて行う。前立腺癌に対する組織内照射も代表的である。全身性の疾患や深部の消化器癌は対象にならない。', 'public', 0, now(),
       '密封小線源治療は、線源を病巣のすぐ近くに置いて狭い範囲に高い線量を与える方法である。この治療が標準的な治療の一つとして行われるのはどれか。',
       '放射線治療（密封小線源）', 0, '', '', 'M', 'llm', 'published', '{"A": "手術と薬物療法が中心であり、密封小線源治療の対象にはならない。", "B": "手術と薬物療法が中心であり、密封小線源治療の対象にはならない。", "D": "手術と薬物療法が中心であり、密封小線源治療の対象にはならない。", "E": "全身性の疾患であり、局所に線源を置く治療にはなじまない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '密封小線源治療は、線源を病巣のすぐ近くに置いて狭い範囲に高い線量を与える方法である。この治療が標準的な治療の一つとして行われるのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "閉所に対する不安がある"}, {"key": "B", "text": "以前にヨード造影剤による重篤な副作用を起こしたことがある"}, {"key": "C", "text": "体内にチタン製のプレートがある"}, {"key": "D", "text": "MRIに対応していない植込み型心臓ペースメーカがある"}, {"key": "E", "text": "妊娠後期である"}]'::jsonb,
       'D', 'MRIは強い静磁場と電磁波を使うため、体内の強磁性体が引き寄せられて動いたり、金属が発熱したりする。MRIに対応していない植込み型心臓ペースメーカや、古い脳動脈瘤クリップは禁忌である。検査室に入る前に、体内の金属と植込み機器、持ち込む物品を必ず確認する。チタンのような非磁性の金属は通常は問題にならない。', 'public', 0, now(),
       'MRI検査の予約にあたり、問診票をもとに体内の金属や植込み機器について確認している。次のうち、MRI検査が禁忌となるのはどれか。',
       'MRIの安全性', 0, '', '', 'M', 'llm', 'published', '{"A": "禁忌ではない。鎮静や開放型の装置で対応できることが多い。", "B": "禁忌ではない。MRIで使う造影剤はガドリニウム製剤であり、ヨードを含まない。", "C": "チタンは強磁性体ではないので、通常は検査できる。", "E": "被ばくが無いので、必要があれば妊娠中でも行える。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = 'MRI検査の予約にあたり、問診票をもとに体内の金属や植込み機器について確認している。次のうち、MRI検査が禁忌となるのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'CBT', '[{"key": "A", "text": "防護衣は散乱線に対しては効果が無い"}, {"key": "B", "text": "透視の時間を延ばしても患者の被ばくは変わらない"}, {"key": "C", "text": "照射野を広げるほど患者の被ばくは減る"}, {"key": "D", "text": "患者の被ばくを減らしても術者の被ばくは変わらない"}, {"key": "E", "text": "線源からの距離が2倍になると、線量率はおよそ4分の1になる"}]'::jsonb,
       'E', '点線源からの線量率は距離の2乗に反比例する。距離・時間・遮蔽が防護の3原則で、なかでも距離をとることは道具を要さず効果が大きい。透視の時間を短くし、照射野を絞ることは患者の被ばくを減らし、その結果として散乱線も減るので術者の防護にもなる。防護衣や天吊りの防護板は散乱線を遮るために使う。', 'public', 0, now(),
       'エックス線透視を使う手技では、患者と術者の双方の被ばくを減らす工夫が要る。放射線防護について正しいのはどれか。',
       '放射線防護', 0, '', '', 'M', 'llm', 'published', '{"A": "防護衣は散乱線を遮るためのもので、透視室で術者を守る主役である。", "B": "透視の時間が延びれば、その分だけ患者の被ばくは増える。", "C": "照射野を広げるほど被ばくする体積も散乱線も増える。絞ることが基本である。", "D": "術者の被ばくはほとんどが患者からの散乱線なので、患者の被ばくを減らすことが術者の防護にもなる。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = 'エックス線透視を使う手技では、患者と術者の双方の被ばくを減らす工夫が要る。放射線防護について正しいのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "日常生活が制限される程度の重い全身疾患をもつ"}, {"key": "B", "text": "全身疾患をもたない健康な患者である"}, {"key": "C", "text": "日常生活が制限されない軽い全身疾患をもつ"}, {"key": "D", "text": "常に生命を脅かす重い全身疾患をもつ"}, {"key": "E", "text": "手術をしなければ生存が期待できない瀕死の状態である"}]'::jsonb,
       'A', 'ASA-PS は術前の全身状態を5段階で表す指標で、緊急手術では末尾に E を付す。健康な患者を1とし、日常生活が制限されない軽度の全身疾患を2、日常生活が制限される高度の全身疾患を3、常に生命を脅かす高度の全身疾患を4、手術をしなければ生存が期待できない瀕死の患者を5とする。周術期の危険の見積もりと術前準備の目安に使う。', 'public', 0, now(),
       '手術の前には全身状態を評価して、周術期の危険を見積もる。米国麻酔科学会の術前全身状態分類〈ASA-PS〉で class 3 に相当するのはどれか。',
       '術前評価', 0, '', '', 'M', 'llm', 'published', '{"B": "class 1 の説明である。", "C": "class 2 の説明である。", "D": "class 4 の説明である。", "E": "class 5 の説明である。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '手術の前には全身状態を評価して、周術期の危険を見積もる。米国麻酔科学会の術前全身状態分類〈ASA-PS〉で class 3 に相当するのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "スキサメトニウム"}, {"key": "B", "text": "ダントロレン"}, {"key": "C", "text": "アトロピン"}, {"key": "D", "text": "ネオスチグミン"}, {"key": "E", "text": "フェンタニル"}]'::jsonb,
       'B', '悪性高熱症は、揮発性吸入麻酔薬やスキサメトニウムを引き金として骨格筋の筋小胞体からカルシウムが過剰に放出され、代謝が暴走する病態である。呼気終末二酸化炭素分圧の上昇が最も早く現れる徴候で、筋硬直・頻脈・高体温・代謝性アシドーシスを伴う。原因薬を直ちに中止し、冷却と全身管理に加えてダントロレンを静脈内投与する。', 'public', 0, now(),
       '全身麻酔中に体温の急激な上昇、呼気終末二酸化炭素分圧の上昇および全身の筋硬直を認めた。直ちに投与すべき薬剤はどれか。',
       '悪性高熱症', 0, '', '', 'M', 'llm', 'published', '{"A": "悪性高熱症の引き金になる薬であり、投与してはならない。", "C": "抗コリン薬であり、悪性高熱症の病態には働かない。", "D": "コリンエステラーゼ阻害薬であり、悪性高熱症の治療薬ではない。", "E": "オピオイドであり、悪性高熱症の治療薬ではない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '全身麻酔中に体温の急激な上昇、呼気終末二酸化炭素分圧の上昇および全身の筋硬直を認めた。直ちに投与すべき薬剤はどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "フルマゼニルの投与"}, {"key": "B", "text": "ナロキソンの投与"}, {"key": "C", "text": "脂肪乳剤の静脈内投与"}, {"key": "D", "text": "局所麻酔薬の追加投与"}, {"key": "E", "text": "カルシウム拮抗薬の投与"}]'::jsonb,
       'C', '局所麻酔薬中毒は血中濃度の上昇により、口の周りのしびれ・耳鳴り・興奮・けいれんといった中枢神経症状から、不整脈や心停止にまで至る。気道確保と換気、けいれんの抑制を行いながら、脂肪乳剤を静脈内投与して血中の局所麻酔薬を取り込ませる。予防としては、投与量の上限を守り、血管内への誤注入を避けることが重要である。', 'public', 0, now(),
       '区域麻酔や局所浸潤麻酔の際には、局所麻酔薬の血中濃度の上昇による中毒に備える。局所麻酔薬中毒に対する治療として推奨されるのはどれか。',
       '局所麻酔薬中毒', 0, '', '', 'M', 'llm', 'published', '{"A": "ベンゾジアゼピンの拮抗薬であり、局所麻酔薬には効かない。", "B": "オピオイドの拮抗薬であり、局所麻酔薬には効かない。", "D": "中毒を悪化させるので、投与は直ちに中止する。", "E": "心抑制を強めるおそれがあり、治療にはならない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '区域麻酔や局所浸潤麻酔の際には、局所麻酔薬の血中濃度の上昇による中毒に備える。局所麻酔薬中毒に対する治療として推奨されるのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "胸郭が挙上する"}, {"key": "B", "text": "両側の呼吸音を聴取する"}, {"key": "C", "text": "経皮的動脈血酸素飽和度が保たれる"}, {"key": "D", "text": "呼気二酸化炭素の波形が連続して得られる"}, {"key": "E", "text": "心窩部で気流音を聴取しない"}]'::jsonb,
       'D', 'カプノグラフィで呼気二酸化炭素の波形が数呼吸にわたって連続して得られることが、気管内への挿管を示す最も確実な所見である。食道挿管を見逃せば致命的になるため、胸郭の動きや呼吸音といった身体所見だけに頼らない。波形が得られない場合は、まず食道挿管を疑ってチューブを抜き、換気をやり直す。', 'public', 0, now(),
       '全身麻酔の導入にあたり気管挿管を行った。チューブが気管内に入っていることの確認として最も信頼できるのはどれか。',
       '気道管理', 0, '', '', 'M', 'llm', 'published', '{"A": "食道挿管でも見かけ上、胸郭が挙上することがある。", "B": "食道挿管でも上腹部からの音が呼吸音のように聞こえることがある。", "C": "前酸素化をしていれば食道挿管でも数分は保たれ、発見が遅れる。", "E": "参考にはなるが、聴取の条件に左右されやすく決め手にはならない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '全身麻酔の導入にあたり気管挿管を行った。チューブが気管内に入っていることの確認として最も信頼できるのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "血圧の上昇"}, {"key": "B", "text": "高体温"}, {"key": "C", "text": "気管支けいれん"}, {"key": "D", "text": "多尿"}, {"key": "E", "text": "血圧の低下"}]'::jsonb,
       'E', '脊髄くも膜下麻酔では交感神経が遮断されて末梢血管が拡張し、静脈還流が減るため血圧が下がる。遮断が胸部の高い位置まで及ぶと心臓交感神経も遮断されて徐脈を伴い、血圧の低下はいっそう強くなる。輸液と昇圧薬で対応し、必要に応じて抗コリン薬を使う。遅れて現れる合併症には硬膜穿刺後頭痛がある。', 'public', 0, now(),
       '下肢の手術のため、脊髄くも膜下麻酔を行った。この麻酔の直後に生じやすいのはどれか。',
       '脊髄くも膜下麻酔', 0, '', '', 'M', 'llm', 'published', '{"A": "交感神経の遮断により、血圧は下がる方向に働く。", "B": "末梢血管の拡張で熱が逃げるため、体温はむしろ下がる。", "C": "脊髄くも膜下麻酔に特徴的な合併症ではない。", "D": "交感神経の遮断で尿閉をきたすことはあるが、多尿にはならない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '下肢の手術のため、脊髄くも膜下麻酔を行った。この麻酔の直後に生じやすいのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "抗凝固薬の影響で凝固能が著しく低下している"}, {"key": "B", "text": "高齢である"}, {"key": "C", "text": "肥満がある"}, {"key": "D", "text": "糖尿病がある"}, {"key": "E", "text": "高血圧がある"}]'::jsonb,
       'A', '硬膜外麻酔の禁忌は、患者の拒否、穿刺部位の感染、出血傾向（抗凝固療法中を含む）、循環血液量の著しい減少、頭蓋内圧の亢進などである。硬膜外血腫は脊髄を圧迫して麻痺を残すため、抗凝固薬や抗血小板薬を使っている患者では、薬ごとに定められた休薬の期間を守り、カテーテルを抜く時期にも同じ配慮をする。', 'public', 0, now(),
       '開腹手術の術後鎮痛のために硬膜外麻酔を併用する方針を検討している。硬膜外麻酔の禁忌はどれか。',
       '硬膜外麻酔', 0, '', '', 'M', 'llm', 'published', '{"B": "禁忌ではない。血圧の低下に注意して行う。", "C": "禁忌ではない。穿刺が難しくなるだけである。", "D": "禁忌ではない。感染や神経障害に注意して行う。", "E": "禁忌ではない。血圧の変動に注意して行う。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '開腹手術の術後鎮痛のために硬膜外麻酔を併用する方針を検討している。硬膜外麻酔の禁忌はどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "ナロキソン塩酸塩"}, {"key": "B", "text": "スガマデクス"}, {"key": "C", "text": "フルマゼニル"}, {"key": "D", "text": "ダントロレン"}, {"key": "E", "text": "アトロピン"}]'::jsonb,
       'B', 'スガマデクスはロクロニウムなどのステロイド骨格をもつ非脱分極性筋弛緩薬を包み込んで不活化し、深い筋弛緩からでも速やかに回復させる。コリンエステラーゼ阻害薬による拮抗と違って、深い遮断にも使え、ムスカリン様の副作用も伴わない。抜管の前には筋弛緩モニターで回復を確かめることが望ましい。', 'public', 0, now(),
       '手術の終わりに筋弛緩が残っていると、換気不全や誤嚥の原因になる。ロクロニウムによる筋弛緩を速やかに回復させる薬剤はどれか。',
       '筋弛緩薬', 0, '', '', 'M', 'llm', 'published', '{"A": "オピオイドの拮抗薬であり、筋弛緩は解除しない。", "C": "ベンゾジアゼピンの拮抗薬であり、筋弛緩は解除しない。", "D": "悪性高熱症の治療薬であり、筋弛緩の回復には用いない。", "E": "抗コリン薬であり、筋弛緩は解除しない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '手術の終わりに筋弛緩が残っていると、換気不全や誤嚥の原因になる。ロクロニウムによる筋弛緩を速やかに回復させる薬剤はどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "男性である"}, {"key": "B", "text": "喫煙者である"}, {"key": "C", "text": "非喫煙者である"}, {"key": "D", "text": "高齢である"}, {"key": "E", "text": "高血圧の治療を受けている"}]'::jsonb,
       'C', '術後悪心・嘔吐の危険因子として確立しているのは、女性であること、喫煙しないこと、術後悪心・嘔吐や動揺病の既往、術後のオピオイドの使用の4つである。当てはまる数が増えるほど起こりやすくなるので、その数に応じて作用機序の異なる制吐薬を組み合わせて予防する。麻酔法の選択や輸液の工夫も予防につながる。', 'public', 0, now(),
       '全身麻酔を予定した患者について、術後悪心・嘔吐〈PONV〉の予防を検討している。この危険因子として確立しているのはどれか。',
       '術後悪心・嘔吐', 0, '', '', 'M', 'llm', 'published', '{"A": "女性のほうが起こりやすく、男性は危険因子ではない。", "B": "喫煙者はむしろ起こりにくいことが知られている。", "D": "高齢者はむしろ起こりにくい。", "E": "危険因子としては確立していない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '全身麻酔を予定した患者について、術後悪心・嘔吐〈PONV〉の予防を検討している。この危険因子として確立しているのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "開口距離が5cmである"}, {"key": "B", "text": "頸部を十分に後屈できる"}, {"key": "C", "text": "Mallampati分類がⅠである"}, {"key": "D", "text": "甲状オトガイ間距離が6cm未満である"}, {"key": "E", "text": "下顎の可動性が保たれている"}]'::jsonb,
       'D', '挿管困難を予測する所見には、開口距離が3cm未満、甲状オトガイ間距離が6cm未満、頸部の後屈の制限、Mallampati分類のⅢからⅣ、小顎症、頸部の腫瘤や放射線治療後の瘢痕などがある。術前に見つけておけば、ビデオ喉頭鏡や声門上器具の準備、意識下挿管といった備えができ、導入後に慌てずに済む。', 'public', 0, now(),
       '全身麻酔を予定した患者の術前診察で、気道の評価を行っている。気管挿管が困難になる可能性を示す所見はどれか。',
       '挿管困難の予測', 0, '', '', 'M', 'llm', 'published', '{"A": "成人では3cm以上あれば開口は十分で、5cmは正常の範囲である。", "B": "後屈ができることは、むしろ挿管しやすい所見である。", "C": "口腔内がよく見える状態であり、挿管しやすい。", "E": "喉頭鏡での視野を得やすく、挿管しやすい。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '全身麻酔を予定した患者の術前診察で、気道の評価を行っている。気管挿管が困難になる可能性を示す所見はどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '麻酔', 2, 'KOKUSHI', '[{"key": "A", "text": "意識消失のあと、長めにマスク換気を行ってから挿管する"}, {"key": "B", "text": "患者が眠るまで吸入麻酔薬の濃度をゆっくり上げていく"}, {"key": "C", "text": "留置されている胃管を導入の前に必ず抜去する"}, {"key": "D", "text": "導入の直前に制酸薬を大量に飲ませる"}, {"key": "E", "text": "十分に酸素を与えたあと、意識消失とほぼ同時に速効性の筋弛緩薬を投与して気管挿管する"}]'::jsonb,
       'E', '迅速導入は、意識消失から気管挿管までの時間を最短にして、胃内容の逆流と誤嚥にさらされる時間を減らす方法である。十分な前酸素化のあと静脈麻酔薬と速効性の筋弛緩薬を続けて投与し、原則としてマスク換気を行わずに挿管して、カフで気道を守る。胃管が入っていれば導入の前に胃内容を吸引しておく。', 'public', 0, now(),
       'イレウスのため緊急手術となり、胃内容の逆流と誤嚥の危険が高いと判断した。この患者の全身麻酔の導入で適切なのはどれか。',
       '迅速導入', 0, '', '', 'M', 'llm', 'published', '{"A": "マスク換気は胃に空気を送り込み、逆流を招く。", "B": "意識消失までの時間が延び、危険にさらされる時間が長くなる。", "C": "胃管は胃内容を抜くために有用であり、抜去する必要はない。", "D": "導入の直前に胃の内容を増やすことになり、かえって危険である。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = 'イレウスのため緊急手術となり、胃内容の逆流と誤嚥の危険が高いと判断した。この患者の全身麻酔の導入で適切なのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'KOKUSHI', '[{"key": "A", "text": "ヨウ素131"}, {"key": "B", "text": "テクネチウム99m"}, {"key": "C", "text": "タリウム201"}, {"key": "D", "text": "ガリウム67"}, {"key": "E", "text": "フッ素18"}]'::jsonb,
       'A', '分化型甲状腺癌（乳頭癌・濾胞癌）の細胞はヨウ素を取り込む性質を残しているため、全摘後の残存甲状腺組織や転移巣にヨウ素131を投与すると、そこから出るβ線で選択的に治療できる。同時にγ線も出るので、集積の分布を画像で確かめられる。治療の前にはヨードを含む食品や造影剤を控えて、取り込みを高めておく。', 'public', 0, now(),
       '甲状腺全摘を受けた分化型甲状腺癌の患者に、放射性ヨウ素内用療法を行うことになった。この治療で用いる核種はどれか。',
       '核医学治療', 0, '', '', 'M', 'llm', 'published', '{"B": "骨シンチグラフィなどの診断に使う核種であり、治療には用いない。", "C": "心筋血流シンチグラフィなどの診断に使う核種である。", "D": "炎症や腫瘍の診断に使う核種である。", "E": "PETのFDGに使う核種であり、診断用である。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '甲状腺全摘を受けた分化型甲状腺癌の患者に、放射性ヨウ素内用療法を行うことになった。この治療で用いる核種はどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'KOKUSHI', '[{"key": "A", "text": "検査の直前に激しい運動をすること"}, {"key": "B", "text": "検査前4〜6時間の絶食"}, {"key": "C", "text": "検査前にブドウ糖を経口投与すること"}, {"key": "D", "text": "検査前日からの絶飲"}, {"key": "E", "text": "検査の直前にインスリンを静脈内投与すること"}]'::jsonb,
       'B', 'FDGはブドウ糖に似た構造をもち、血糖が高いと腫瘍への集積が下がる。そのため検査前4〜6時間は絶食して血糖を下げておく。水は飲んでよく、検査後は排泄を促すために多めに飲むよう勧める。直前の運動やインスリンの投与は骨格筋への集積を増やすので避ける。糖尿病の患者では血糖の管理について事前に相談しておく。', 'public', 0, now(),
       '悪性腫瘍の検索のためFDG-PET検査を予定した患者に、検査当日の過ごし方を説明する。前処置として適切なのはどれか。',
       '核医学の前処置', 0, '', '', 'M', 'llm', 'published', '{"A": "骨格筋への集積が増えて読影の妨げになる。", "C": "血糖が上がり、腫瘍への集積が下がる。", "D": "水分を控える必要はなく、脱水はかえって望ましくない。", "E": "筋肉への取り込みが増え、読影の妨げになる。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '悪性腫瘍の検索のためFDG-PET検査を予定した患者に、検査当日の過ごし方を説明する。前処置として適切なのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'KOKUSHI', '[{"key": "A", "text": "腹部単純CT"}, {"key": "B", "text": "腹部造影CT"}, {"key": "C", "text": "腹部超音波検査"}, {"key": "D", "text": "腹部単純エックス線撮影"}, {"key": "E", "text": "注腸造影"}]'::jsonb,
       'C', '急性虫垂炎の画像診断では、被ばくの影響を受けやすい小児・妊婦・若年女性でまず超音波を行い、診断が付かないときにCTへ進むのが標準的な考え方である。超音波では腫大した虫垂や周囲の脂肪織の変化をとらえる。検査を選ぶときは、診断能だけでなく被ばくと侵襲を合わせて考える。', 'public', 0, now(),
       '20歳の女性。右下腹部痛を主訴に来院し、急性虫垂炎が疑われた。被ばくを避ける観点から第一に選ぶ画像検査はどれか。',
       '画像検査の選択', 0, '', '', 'M', 'llm', 'published', '{"A": "診断能は高いが被ばくを伴うので、若年女性では第一選択にはしない。", "B": "被ばくに加えて、ヨード造影剤の副作用も問題になる。", "D": "虫垂炎の診断には役立たず、被ばくだけが残る。", "E": "急性腹症では穿孔の危険があり、虫垂炎の診断には用いない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '20歳の女性。右下腹部痛を主訴に来院し、急性虫垂炎が疑われた。被ばくを避ける観点から第一に選ぶ画像検査はどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'KOKUSHI', '[{"key": "A", "text": "気管支喘息の患者"}, {"key": "B", "text": "妊娠中の女性"}, {"key": "C", "text": "鉄欠乏性貧血の患者"}, {"key": "D", "text": "透析を受けている慢性腎臓病の患者"}, {"key": "E", "text": "甲状腺機能亢進症の患者"}]'::jsonb,
       'D', '腎性全身性線維症はガドリニウム造影剤の投与後に皮膚や内臓が硬くなる重篤な合併症で、重度の腎機能障害、とりわけ透析を受けている患者で危険が高い。造影MRIの前には腎機能を確かめ、必要性を検討したうえで、体内に残りにくい製剤を必要最小限の量で使う。腎機能が保たれていればまず起こらない。', 'public', 0, now(),
       '腎機能が低下した患者に造影MRIを行う際には、腎性全身性線維症〈NSF〉に注意する。この発症のリスクが最も高いのはどれか。',
       'ガドリニウム造影剤', 0, '', '', 'M', 'llm', 'published', '{"A": "造影剤の過敏反応の危険因子ではあるが、腎性全身性線維症とは別である。", "B": "投与は慎重に判断するが、腎性全身性線維症の危険因子ではない。", "C": "腎性全身性線維症とは関係しない。", "E": "問題になるのはヨード造影剤のほうで、ガドリニウム造影剤では問題にならない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '腎機能が低下した患者に造影MRIを行う際には、腎性全身性線維症〈NSF〉に注意する。この発症のリスクが最も高いのはどれか。');

INSERT INTO quiz_question (
    category, difficulty, exam_type, choices, correct_choice_key,
    explanation, visibility, correct_rate, created_at, question_text,
    topic, answer_count, blueprint_code, class_group, question_type,
    source, status, choice_explanations)
SELECT '放射線', 2, 'KOKUSHI', '[{"key": "A", "text": "早期胃癌に対する内視鏡的粘膜下層剥離術"}, {"key": "B", "text": "胆石症に対する腹腔鏡下胆囊摘出術"}, {"key": "C", "text": "尿管結石に対する体外衝撃波結石破砕術"}, {"key": "D", "text": "前立腺癌に対する外部からの放射線治療"}, {"key": "E", "text": "肝細胞癌に対する肝動脈化学塞栓療法"}]'::jsonb,
       'E', '画像下治療は、エックス線透視・超音波・CTで体内を見ながらカテーテルや針を進めて治療する方法である。肝細胞癌に対する肝動脈化学塞栓療法のほか、外傷や消化管出血に対する動脈塞栓術、血管形成術とステント留置、膿瘍のドレナージ、経皮的生検などが代表である。開腹を避けられ、体への負担が小さい点が利点である。', 'public', 0, now(),
       '画像下治療〈IVR〉は、画像で体内を見ながらカテーテルや針を進めて治療する方法である。この画像下治療として行われるのはどれか。',
       '画像下治療', 0, '', '', 'M', 'llm', 'published', '{"A": "内視鏡で行う治療であり、画像下治療には含まれない。", "B": "腹腔鏡下の手術であり、画像下治療には含まれない。", "C": "体外から衝撃波を当てる治療であり、画像下治療には含まれない。", "D": "放射線治療であり、画像下治療には含まれない。"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM quiz_question WHERE question_text = '画像下治療〈IVR〉は、画像で体内を見ながらカテーテルや針を進めて治療する方法である。この画像下治療として行われるのはどれか。');

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
           ('quiz', '0008_strip_explanation_boilerplate'),
           ('quiz', '0009_question_choice_explanations'),
           ('quiz', '0010_backfill_choice_explanations'),
           ('quiz', '0011_merge_toxicology_into_emergency'),
           ('quiz', '0012_tumor_marker_choices_abbreviation_only'),
           ('quiz', '0013_merge_emergency_family'),
           ('quiz', '0014_reclassify_radiology_questions'),
           ('quiz', '0015_merge_urology_into_kidney'),
           ('quiz', '0016_consolidate_small_subjects'),
           ('quiz', '0017_split_kidney_and_urology'),
           ('quiz', '0018_unpack_series_and_align_categories'),
           ('quiz', '0019_split_radiology_and_anesthesia'),
           ('quiz', '0020_strip_stray_column_separators'),
           ('quiz', '0021_question_report_reasons'),
           ('exams', '0007_monthly_kokushi_is_for_fifth_year_and_up'),
           ('exams', '0008_rename_cbt_once_title'),
           ('exams', '0009_alter_mockexam_kind_label'),
           ('exams', '0010_cbt_exam_yearly_window')
       ) AS v(app, name)
 WHERE NOT EXISTS (
       SELECT 1 FROM django_migrations d WHERE d.app = v.app AND d.name = v.name);

COMMIT;
