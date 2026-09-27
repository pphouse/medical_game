-- accounts.0010_deletedaccount を本番に当てる。何度流しても結果は同じ。
--
-- **デプロイの前に流すこと。** この表が無いまま新しいコードが動くと、
-- SupabaseJWTAuthentication が退会済みかどうかをここに問い合わせるため、
-- ログイン中のリクエストが全部 500 になる。
--
-- django_migrations にも記録するので、あとで manage.py migrate を通しても
-- 二重に作ろうとしない。
BEGIN;

CREATE TABLE IF NOT EXISTS "accounts_deletedaccount" (
    "id" uuid NOT NULL PRIMARY KEY,
    "deleted_at" timestamp with time zone NOT NULL
);

-- 新しい表は default privileges により anon/authenticated への grant が付かない
-- が、supabase/migrations/20260723000100_rls_lockdown.sql と同じ方針で RLS も
-- 有効にしておく。ポリシーを作らないので Data API からは全部拒否になる
-- （Django は所有者 postgres で繋ぐので影響しない）。
ALTER TABLE "accounts_deletedaccount" ENABLE ROW LEVEL SECURITY;

INSERT INTO django_migrations (app, name, applied)
SELECT 'accounts', '0010_deletedaccount', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM django_migrations
    WHERE app = 'accounts' AND name = '0010_deletedaccount'
);

COMMIT;
