-- 本文が空の設問を洗い出す診断クエリ（読み取りのみ・変更なし）。
--
-- 分野別演習の一覧に「（本文なし）」と出るのは、frontend の QuestionPicker が
-- case_stem も question_text も空のときに出すフォールバック文言。リポジトリ側の
-- JSON には空の本文が1件も無いので、本番DBの行だけが壊れている（取り込み後に
-- 壊れたか、修復前のデータが入ったまま）と考えられる。どの行がどう壊れて
-- いるかを確定させる。Supabase の SQL Editor にそのまま貼れる。

-- 1) 規模。exam_type / source / status ごとの内訳。
SELECT
    exam_type,
    source,
    status,
    count(*) AS empty_body,
    count(*) FILTER (WHERE question_set_id IS NOT NULL) AS in_question_set
FROM quiz_question
WHERE btrim(coalesce(question_text, '')) = ''
GROUP BY exam_type, source, status
ORDER BY empty_body DESC;

-- 2) 実際の行。blueprint_code があればリポジトリの JSON と突き合わせて本文を
--    復元できる（国試は "114-A-1" 形式で 1153 件すべて一意）。
SELECT
    id,
    blueprint_code,
    exam_type,
    category,
    question_set_id,
    length(coalesce(question_text, '')) AS body_len,
    length(coalesce(explanation, ''))   AS expl_len,
    jsonb_array_length(choices::jsonb)  AS n_choices,
    left(coalesce(explanation, ''), 60) AS expl_head
FROM quiz_question
WHERE btrim(coalesce(question_text, '')) = ''
ORDER BY exam_type, blueprint_code, id;

-- 3) 本文はあるが選択肢が壊れている／文字化けが残っている行。
--    国試には「散瞳を認めるのはどれか。」のような短文が正常に存在するので、
--    短さだけでは異常と判定できない。選択肢の欠けと不正文字で見る。
--    U+FFFD (置換文字) と制御文字を含む行を拾う。
SELECT
    id, blueprint_code, exam_type, category,
    length(question_text) AS body_len,
    jsonb_array_length(choices::jsonb) AS n_choices,
    left(question_text, 40) AS body_head
FROM quiz_question
WHERE btrim(coalesce(question_text, '')) <> ''
  AND (jsonb_array_length(choices::jsonb) < 2
       OR question_text LIKE '%' || U&'\FFFD' || '%'
       OR question_text ~ '[\u0000-\u0008\u000B-\u001F\u007F-\u009F]')
ORDER BY exam_type, blueprint_code, id;

-- 4) 国試の解説がプレースホルダ（「準備中」）のままの件数。
SELECT exam_type, count(*) AS placeholder_explanations
FROM quiz_question
WHERE explanation LIKE '%詳しい解説は準備中%'
GROUP BY exam_type;
