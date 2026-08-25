-- 本番DBの分野名を正典に寄せる（quiz/categories.py の CATEGORY_ALIASES と同じ対応）
-- 追加・削除はせず、既存行の category を書き換えるだけ。
BEGIN;
UPDATE quiz_question SET category = '免疫・アレルギー' WHERE category = '免疫・アレルギー・膠原病';
UPDATE quiz_question SET category = '内分泌・代謝系' WHERE category = '内分泌';
UPDATE quiz_question SET category = '内分泌・代謝系' WHERE category = '内分泌・代謝';
UPDATE quiz_question SET category = '呼吸器系' WHERE category = '呼吸器';
UPDATE quiz_question SET category = '小児系' WHERE category = '小児';
UPDATE quiz_question SET category = '循環器系' WHERE category = '循環器';
UPDATE quiz_question SET category = '救急系' WHERE category = '救急';
UPDATE quiz_question SET category = '救急系' WHERE category = '救急・中毒';
UPDATE quiz_question SET category = '泌尿器系' WHERE category = '泌尿器';
UPDATE quiz_question SET category = '消化器系' WHERE category = '消化器';
UPDATE quiz_question SET category = '産婦人科系' WHERE category = '産婦人科';
UPDATE quiz_question SET category = '皮膚系' WHERE category = '皮膚';
UPDATE quiz_question SET category = '眼系' WHERE category = '眼';
UPDATE quiz_question SET category = '神経系' WHERE category = '神経';
UPDATE quiz_question SET category = '精神系' WHERE category = '精神';
UPDATE quiz_question SET category = '耳鼻咽喉系' WHERE category = '耳鼻咽喉';
UPDATE quiz_question SET category = '腎・尿路系' WHERE category = '腎・尿路系（体液・電解質バランスを含む）';
UPDATE quiz_question SET category = '血液・造血器・リンパ系' WHERE category = '血液';
UPDATE quiz_question SET category = '血液・造血器・リンパ系' WHERE category = '血液・造血器系';
UPDATE quiz_question SET category = '運動器系' WHERE category = '運動器';
-- 寄せ切れなかった名前が残っていないか確認する
SELECT category, count(*) AS n FROM quiz_question GROUP BY 1 ORDER BY 1;
COMMIT;
