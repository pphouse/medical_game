// Supabase Edge Function: pg_cron から呼ばれ、Django の internal API を叩く
// 汎用トリガ (spec 3-3 案A: 集計定義を Django 側に一本化し二重管理を避ける)。
//
// デプロイ:
//   supabase functions deploy call-internal --no-verify-jwt
//   supabase secrets set DJANGO_ORIGIN=https://<django-host> INTERNAL_API_TOKEN=<token>
//
// 呼び出し (pg_cron 側は supabase/migrations/20260723001000_cron_schedules.sql):
//   POST /functions/v1/call-internal  body: {"path": "/api/internal/aggregate/", "payload": {...}}

Deno.serve(async (req) => {
  const origin = Deno.env.get("DJANGO_ORIGIN");
  const token = Deno.env.get("INTERNAL_API_TOKEN");
  if (!origin || !token) {
    return new Response("DJANGO_ORIGIN / INTERNAL_API_TOKEN not configured", { status: 500 });
  }

  let body: { path?: string; payload?: unknown } = {};
  try {
    body = await req.json();
  } catch {
    // empty body is fine — defaults below
  }
  const path = body.path ?? "/api/internal/aggregate/";
  if (!path.startsWith("/api/internal/")) {
    return new Response("path must start with /api/internal/", { status: 400 });
  }

  const res = await fetch(`${origin}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Token": token,
    },
    body: JSON.stringify(body.payload ?? {}),
  });

  return new Response(await res.text(), {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
});
