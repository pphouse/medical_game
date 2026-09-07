-- 本番に「解説準備中」のまま published で残っていた国試7問を直す。
-- 何度流しても結果は同じ。
--
-- 内訳（diagnose_missing_explanations.sql の結果どおり）:
--   ・119-C-2   … 本文の冒頭が欠け、正答も誤っている（D → 正しくは B）
--   ・その他6問 … 図表がないと解けない
--
-- 119-C-44 の内容は kokushi_119.json から、取り込みと同じ変換
-- （import_questions.build_explanation / convert_choices）を通して生成した。

BEGIN;

-- (1) 119-C-2 を、正しい 119-C-44 の内容に直す。
--
-- 取り込み時に症例文の折り返し「2 日前から下腹部痛も…」を設問番号の行と
-- 取り違えて切り出したため本文の冒頭が欠け、正答表の照合先も C002 にずれて
-- D が入っていた。正しくは B「妊娠反応検査」。生殖年齢の女性の不正性器出血で
-- D「子宮内膜組織診」を正答として出すのは実害があるため、これが最優先。
UPDATE quiz_question SET
    blueprint_code      = '119-C-44',
    question_text       = '40歳の女性。性器出血の持続を主訴に来院した。5日前から性器出血を認め、2日前から下腹部痛も伴うようになった。最終月経は4週間前。月経周期は30〜60日、不整、持続5日間。身長153cm、体重50kg。体温36.5°C。脈拍80/分、整。血圧118/64mmHg。呼吸数18/分。腹部は平坦、軟で、肝・脾を触知しない。最初に行う対応はどれか。',
    choices             = '[{"key": "A", "text": "腹部単純CT"}, {"key": "B", "text": "妊娠反応検査"}, {"key": "C", "text": "経腟超音波検査"}, {"key": "D", "text": "子宮内膜組織診"}, {"key": "E", "text": "プロゲステロン投与"}]'::jsonb,
    correct_choice_key  = 'B',
    category            = '産科',
    difficulty          = 2,
    explanation         = '正答は B「妊娠反応検査」。

生殖年齢の女性の不正性器出血では、まず妊娠の有無を確かめる。異所性妊娠や流産を見落とせば命に関わるため、月経不順であっても妊娠反応検査が最初の一歩になる。

出典：厚生労働省ホームページ 第119回医師国家試験 C044',
    choice_explanations = '{"A": "被曝を伴い、妊娠の可能性を否定する前に行うべきではない。", "C": "経腟超音波検査は次に行う重要な検査だが、妊娠反応の結果があってこそ所見を解釈できる。", "D": "子宮内膜組織診は子宮体癌を疑うときに行う。妊娠の可能性を否定してからである。", "E": "プロゲステロン投与は原因を確かめずに行うもので、妊娠中であれば診断を遅らせる。"}'::jsonb
WHERE exam_type = 'KOKUSHI' AND blueprint_code = '119-C-2';

-- (2) 図表がないと解けない6問を非公開にする。
--
-- 削除しないのは、解答履歴が FK の CASCADE でぶら下がっているため。
-- 消すと、この問題を解いた人の学習記録まで一緒に消える。
UPDATE quiz_question SET status = 'rejected'
WHERE exam_type = 'KOKUSHI'
  AND status = 'published'
  AND blueprint_code IN ('114-C-14', '117-C-30', '117-E-22', '117-F-33', '119-C-15', '119-C-22');

-- 確認 (a): 公開中で解説が入っていない国試。0行なら完了。
SELECT blueprint_code, status FROM quiz_question
WHERE exam_type = 'KOKUSHI' AND status = 'published'
  AND (explanation IS NULL OR explanation LIKE '%準備中%');

-- 確認 (b): 直した1問。正答が B、本文が171字になっていること。
SELECT blueprint_code, correct_choice_key, category,
       length(question_text) AS text_len,
       jsonb_object_keys(choice_explanations) AS rationale_keys
FROM quiz_question WHERE blueprint_code = '119-C-44';

-- 確認 (c): 正答が誤っていた間に記録された解答の数。
-- 0 でなければ、その履歴の正誤は誤った正答キーで判定されている。
SELECT count(*) AS affected_answer_histories
FROM quiz_answerhistory h
JOIN quiz_question q ON q.id = h.question_id
WHERE q.blueprint_code = '119-C-44';

COMMIT;
