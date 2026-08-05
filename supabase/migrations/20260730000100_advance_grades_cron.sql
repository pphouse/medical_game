-- 学年の自動繰り上げ (spec: 4年生→5年生などの進級で模試のCBT/国試表示が
-- 自動で切り替わるよう、年度切り替え（4月1日）に合わせてProfile.gradeを
-- 一斉に+1する)。既存の call-internal Edge Function をそのまま再利用する
-- （supabase/migrations/20260723001000_cron_schedules.sql と同じ仕組み）。
--
-- 適用前に置換すること: <project-ref> … Supabase プロジェクトの ref
-- （edge_anon_key シークレットは cron_schedules.sql 適用時に作成済みのはず）

-- 毎年4月1日 0:10 JST (= 3/31 15:10 UTC) に全学生の学年を1つ繰り上げる
select cron.schedule(
  'advance-grades-yearly',
  '10 15 31 3 *',
  $$
  select net.http_post(
    url := 'https://<project-ref>.supabase.co/functions/v1/call-internal',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'edge_anon_key')
    ),
    body := jsonb_build_object('path', '/api/internal/advance-grades/')
  );
  $$
);
