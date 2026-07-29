-- Phase 0: deny-by-default lockdown (spec 1.4).
--
-- Django connects as the table owner (postgres), which is NOT subject to
-- RLS, so none of this affects the backend. It removes the Supabase Data
-- API's (PostgREST) implicit access for anon/authenticated so that no
-- Django-managed table is readable with the anon key.
--
-- Frontend-facing exceptions (battle tables, profiles view, claim_buzz RPC)
-- are granted back explicitly in later migration files.
--
-- Re-run this file after applying new Django migrations so newly created
-- tables get locked down too (it is idempotent).

-- 1) Drop all direct grants for API roles on existing objects.
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;

-- 2) Future objects created by postgres (= Django migrations) get no API
--    grants either.
alter default privileges for role postgres in schema public
  revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all on functions from anon, authenticated;

-- 3) Belt and braces: enable RLS on every table in public. With no
--    policies defined this denies everything even if a grant slips back in.
do $$
declare r record;
begin
  for r in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', r.tablename);
  end loop;
end $$;
