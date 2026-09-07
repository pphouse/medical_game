-- 本番に当たっていないマイグレーションを洗い出す。読むだけで何も変えない。
--
-- fix_published_kokushi.sql が
--   ERROR: column "choice_explanations" ... does not exist
-- で落ちる場合、quiz.0009 が未適用。列を足してから流す必要がある。

-- (1) 列があるか。choice_explanations が無ければ quiz.0009 が未適用。
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'quiz_question'
  AND column_name IN ('choice_explanations', 'blueprint_code', 'correct_choice_key', 'choices')
ORDER BY column_name;

-- (2) django_migrations の記録。ここに無いものは当たっていない。
SELECT app, name, applied
FROM django_migrations
WHERE app IN ('quiz', 'accounts', 'exams')
ORDER BY app, name;

-- (3) リポジトリにあって本番に無いもの（下の一覧と (2) を突き合わせる）。
--   quiz     : 0001…0008 / 0009_question_choice_explanations
--                        / 0010_backfill_choice_explanations
--   accounts : 0001…0009 / 0010_deletedaccount
--   exams    : 0001…0007

-- (4) 解説がまだ本文に畳み込まれたままの公開中の国試。
--     (1) で列が無ければこの問い合わせはエラーになる（それ自体が答え）。
SELECT count(*) AS folded_kokushi
FROM quiz_question
WHERE exam_type = 'KOKUSHI' AND status = 'published'
  AND explanation LIKE '%【誤答選択肢の解説】%';
