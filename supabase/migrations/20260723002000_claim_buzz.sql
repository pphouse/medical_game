-- Phase 4: 早押し RPC (spec 4-1/4-2).
--
-- 早押し順序はサーバ時刻 (clock_timestamp()) で決定する。クライアントから
-- 送られたタイムスタンプは一切信用しない。SECURITY DEFINER で RLS を
-- バイパスしつつ、参加者チェックを関数内で行う。
-- 同時押しは pg_advisory_xact_lock(round_id) で直列化し、rank の一意性を
-- 保証する（INSERT 衝突は UNIQUE(round_id, profile_id) が防ぐ）。

create or replace function public.claim_buzz(p_round_id bigint)
returns table (buzz_id bigint, buzz_rank smallint)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile uuid := auth.uid();
  v_room_id bigint;
  v_rank smallint;
  v_id bigint;
begin
  if v_profile is null then
    raise exception 'not authenticated';
  end if;

  select r.room_id into v_room_id
  from battle_battleround r
  where r.id = p_round_id
    and r.revealed_at is not null
    and r.closed_at is null;
  if v_room_id is null then
    raise exception 'round is not open';
  end if;

  perform 1 from battle_battleparticipant p
  where p.room_id = v_room_id and p.user_id = v_profile;
  if not found then
    raise exception 'not a participant of this room';
  end if;

  -- ラウンド単位で直列化して rank を確定させる
  perform pg_advisory_xact_lock(p_round_id);

  -- 二重押しは既存の rank を返す（冪等・ラウンドあたり1回, spec 6 レート制限）
  select b.id, b.rank into v_id, v_rank
  from battle_battlebuzz b
  where b.round_id = p_round_id and b.profile_id = v_profile;
  if v_id is not null then
    return query select v_id, v_rank;
    return;
  end if;

  select count(*) + 1 into v_rank
  from battle_battlebuzz b
  where b.round_id = p_round_id;

  insert into battle_battlebuzz
    (round_id, profile_id, buzzed_at, selected_choice_key, is_correct, rank)
  values
    (p_round_id, v_profile, clock_timestamp(), '', null, v_rank)
  returning id into v_id;

  return query select v_id, v_rank;
end;
$$;

revoke all on function public.claim_buzz(bigint) from public;
grant execute on function public.claim_buzz(bigint) to authenticated;
