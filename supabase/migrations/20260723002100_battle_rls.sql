-- Phase 4: 対戦テーブルの RLS + Realtime (spec 1.4).
--
-- フロントが supabase-js で直接触るのは:
--   * battle_battleround / battle_battlebuzz / battle_battleparticipant の
--     SELECT（自分が参加中のルームのみ）+ Realtime 購読
--   * INSERT は RPC (claim_buzz) 経由のみ — テーブルへの INSERT 権限は
--     付与しない
-- battle_battleroom は Django API 経由で操作するため直接 SELECT も
-- 参加者のみに限定する。

-- 参加判定ヘルパ（RLS ポリシー内の再帰を避けるため SECURITY DEFINER）
create or replace function public.is_battle_participant(p_room_id bigint)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1 from battle_battleparticipant p
    where p.room_id = p_room_id and p.user_id = auth.uid()
  );
$$;

revoke all on function public.is_battle_participant(bigint) from public;
grant execute on function public.is_battle_participant(bigint) to authenticated;

alter table public.battle_battleroom enable row level security;
alter table public.battle_battleparticipant enable row level security;
alter table public.battle_battleround enable row level security;
alter table public.battle_battlebuzz enable row level security;

grant select on public.battle_battleroom to authenticated;
grant select on public.battle_battleparticipant to authenticated;
grant select on public.battle_battleround to authenticated;
grant select on public.battle_battlebuzz to authenticated;

drop policy if exists "rooms: participants select" on public.battle_battleroom;
create policy "rooms: participants select"
  on public.battle_battleroom for select
  to authenticated
  using (public.is_battle_participant(id));

drop policy if exists "participants: same-room select" on public.battle_battleparticipant;
create policy "participants: same-room select"
  on public.battle_battleparticipant for select
  to authenticated
  using (public.is_battle_participant(room_id));

drop policy if exists "rounds: participants select" on public.battle_battleround;
create policy "rounds: participants select"
  on public.battle_battleround for select
  to authenticated
  using (public.is_battle_participant(room_id));

drop policy if exists "buzzes: participants select" on public.battle_battlebuzz;
create policy "buzzes: participants select"
  on public.battle_battlebuzz for select
  to authenticated
  using (
    exists (
      select 1 from battle_battleround r
      where r.id = round_id and public.is_battle_participant(r.room_id)
    )
  );

-- Realtime: ラウンド公開・早押し・スコア変化を購読できるようにする
do $$
begin
  alter publication supabase_realtime add table public.battle_battleround;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.battle_battlebuzz;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.battle_battleparticipant;
exception when duplicate_object then null;
end $$;
