-- 本文が空の15行を丸ごと出す（読み取りのみ・DBは一切変更しない）。
--
-- 直前の切り分けで分かったこと:
--   ・本文が空なのは15行だけ（CBT 10 / 国試 5）
--   ・国試の5行に 114-A-9 形式の blueprint_code が無い
--     → 修復SQLの (1) blueprint_code で当てる経路は当たらない
--   ・選択肢は15行とも無事
--     → (2) 選択肢の指紋で当てる経路なら当たる可能性がある
--
-- その15行が同梱データのどの設問なのかを、選択肢の中身で照合したい。
-- 結果は1セルのJSONで返るので、そのままコピーして貼ってほしい。
-- 本文は空なので個人情報や答えは含まれない。

SELECT jsonb_pretty(jsonb_agg(t ORDER BY t.exam_type, t.id))
FROM (
    SELECT id,
           exam_type,
           category,
           blueprint_code,
           status,
           source,
           question_set_id,
           correct_choice_key,
           left(coalesce(explanation, ''), 60) AS explanation_head,
           choices::jsonb                      AS choices
    FROM quiz_question
    WHERE btrim(coalesce(question_text, '')) = ''
) AS t;
