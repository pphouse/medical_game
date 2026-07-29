-- Phase 3: ランキング集計の定期実行 (spec 3-3).
--
-- 実行頻度: 全期間は1日1回、当月は1時間毎。pg_cron から直接 Django コマンド
-- は叩けないため、Edge Function `call-internal` 経由で Django の
-- /api/internal/aggregate/ を呼ぶ（案A）。
--
-- 適用前に置換すること:
--   <project-ref>  … Supabase プロジェクトの ref
-- また、Edge Function 呼び出し用の anon key を Vault に保存しておく:
--   select vault.create_secret('<anon-key>', 'edge_anon_key');

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 当月分: 毎時5分
select cron.schedule(
  'aggregate-rankings-hourly',
  '5 * * * *',
  $$
  select net.http_post(
    url := 'https://<project-ref>.supabase.co/functions/v1/call-internal',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'edge_anon_key')
    ),
    body := jsonb_build_object(
      'path', '/api/internal/aggregate/',
      'payload', jsonb_build_object('periods', array[to_char(now() at time zone 'Asia/Tokyo', 'YYYY-MM')])
    )
  );
  $$
);

-- 全期間: 毎日 18:20 UTC (= JST 3:20)
select cron.schedule(
  'aggregate-rankings-daily',
  '20 18 * * *',
  $$
  select net.http_post(
    url := 'https://<project-ref>.supabase.co/functions/v1/call-internal',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'edge_anon_key')
    ),
    body := jsonb_build_object(
      'path', '/api/internal/aggregate/',
      'payload', jsonb_build_object('periods', array['all'])
    )
  );
  $$
);
