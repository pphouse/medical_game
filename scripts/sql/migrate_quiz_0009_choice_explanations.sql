-- quiz.0009_question_choice_explanations を本番に当てる。何度流しても結果は同じ。
--
-- fix_published_kokushi.sql と kokushi_choice_explanations.sql は
-- この列に書き込むので、**この SQL を最初に流すこと。**
-- 未適用のまま流すと
--   ERROR: column "choice_explanations" of relation "quiz_question" does not exist
-- で落ちる。
--
-- 新しいコードもこの列を読むので、デプロイ前に当てておく必要がある。
--
-- Django の JSONField(default=dict) は NOT NULL + サーバ側の既定値なしで作られ、
-- 既定値は Python 側が入れる。既存行を埋めるために一度だけ DEFAULT を付けて
-- から外し、Django が makemigrations で差分を出さない形に揃える。
BEGIN;

ALTER TABLE "quiz_question"
    ADD COLUMN IF NOT EXISTS "choice_explanations" jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE "quiz_question"
    ALTER COLUMN "choice_explanations" DROP DEFAULT;

INSERT INTO django_migrations (app, name, applied)
SELECT 'quiz', '0009_question_choice_explanations', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM django_migrations
    WHERE app = 'quiz' AND name = '0009_question_choice_explanations'
);

-- 確認: 列ができ、既存行が空の辞書で埋まっていること。
SELECT count(*) AS total,
       count(*) FILTER (WHERE choice_explanations = '{}'::jsonb) AS empty_dict
FROM quiz_question;

COMMIT;
