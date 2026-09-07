-- 解説が入っていない国試を特定する。読み取りのみ。
-- kokushi_explanations.sql は blueprint_code で照合しているので、
-- 新しいデータ側に無いコードの行だけが取り残される。
SELECT
    blueprint_code            AS "コード",
    status                    AS "公開状態",
    correct_choice_key        AS "正答",
    length(question_text)     AS "本文の長さ",
    left(replace(question_text, E'\n', ' '), 60) AS "本文の冒頭"
FROM quiz_question
WHERE exam_type = 'KOKUSHI'
  AND (explanation IS NULL OR explanation LIKE '%準備中%')
ORDER BY blueprint_code;
