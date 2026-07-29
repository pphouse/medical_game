-- Phase 0: profile visibility for direct supabase-js access (spec 1.4).
--
-- accounts_profile is Django-managed; its PK equals auth.users.id.
--   * Own row: SELECT + UPDATE(display_name, grade) allowed.
--   * Other users: only display_name / university_id, via the
--     public_profiles view (definer view, bypasses base-table RLS).

-- Column-scoped grants for the base table.
grant select on public.accounts_profile to authenticated;
grant update (display_name, grade) on public.accounts_profile to authenticated;

alter table public.accounts_profile enable row level security;

drop policy if exists "profiles: select own" on public.accounts_profile;
create policy "profiles: select own"
  on public.accounts_profile for select
  to authenticated
  using (id = (select auth.uid()));

drop policy if exists "profiles: update own" on public.accounts_profile;
create policy "profiles: update own"
  on public.accounts_profile for update
  to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

-- Public subset of every profile (display name + university only — never
-- email; Supabase Auth emails stay in auth.users which is not exposed).
create or replace view public.public_profiles
  with (security_invoker = off) as
  select id, display_name, university_id
  from public.accounts_profile;

grant select on public.public_profiles to authenticated;
