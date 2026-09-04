-- 「（本文なし）」の切り分け（読み取りのみ・DBは一切変更しない）。
--
-- アプリの分野別演習で「（本文なし）」と出るのは、frontend の QuestionPicker が
-- case_stem も question_text も空のときに出す文言。一覧は id の昇順に並ぶので、
-- 「循環器の最初の2問」はこの (2) の先頭2行にあたる。
--
-- リポジトリの同梱データ側は全2,249問とも本文が入っており、履歴を遡っても空
-- だったことは一度も無い。APIも question_text をそのまま返している（絞り込み
-- なし）。したがって本番DBの行を見ないと切り分けできない。
--
-- Supabase の SQL Editor にそのまま貼って、5つの結果をそのまま返してほしい。


-- (1) いま本文が空の行はどれくらいあるか。0件なら別の原因を探す。
SELECT exam_type,
       count(*) FILTER (WHERE btrim(coalesce(question_text, '')) = '') AS 本文が空,
       count(*)                                                        AS 全件
FROM quiz_question
GROUP BY exam_type ORDER BY exam_type;


-- (2) 循環器（国試）を一覧と同じ並び（id昇順）で先頭10件。
--     本文の長さが0なら本文が消えている。長さがあるのに画面が「本文なし」なら
--     原因は別（表示側かキャッシュ）。
SELECT id,
       blueprint_code,
       status,
       source,
       length(coalesce(question_text, ''))  AS 本文の長さ,
       left(coalesce(question_text, ''), 40) AS 本文の冒頭,
       question_set_id                       AS 連問の親,
       jsonb_array_length(choices::jsonb)    AS 選択肢の数
FROM quiz_question
WHERE exam_type = 'KOKUSHI' AND category = '循環器'
ORDER BY id
LIMIT 10;


-- (3) 修復SQLを流したかどうかの確認。
--     解説が「準備中」のままなら kokushi_explanations は未実行。
SELECT count(*) FILTER (WHERE explanation LIKE '%詳しい解説は準備中%') AS 解説が準備中のまま,
       count(*) FILTER (WHERE explanation LIKE '正答は%')               AS 解説が入っている,
       count(*)                                                          AS 国試の全件
FROM quiz_question WHERE exam_type = 'KOKUSHI';


-- (4) 科目の統合を流したかどうかの確認。0行なら実行済み。
SELECT category, count(*)
FROM quiz_question
WHERE category IN ('救急', '中毒', '麻酔科', '中毒・環境')
GROUP BY category;


-- (5) 本文が空の行のうち、修復SQLで当てられるものが何件あるか。
--     国試は blueprint_code、CBT は選択肢の指紋で当てている。
--     選択肢まで壊れている行はどちらでも当たらないので、ここで分かる。
SELECT exam_type,
       count(*)                                                   AS 本文が空,
       count(*) FILTER (WHERE blueprint_code ~ '^\d+-[A-F]-\d+$') AS 国試コードあり,
       count(*) FILTER (WHERE choices IS NULL
                           OR jsonb_array_length(choices::jsonb) = 0) AS 選択肢も壊れている
FROM quiz_question
WHERE btrim(coalesce(question_text, '')) = ''
GROUP BY exam_type ORDER BY exam_type;
