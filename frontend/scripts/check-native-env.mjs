// iOS アプリのバンドルは「作った瞬間の環境変数」で固まる。ブラウザ版と違い
// 後から向き先を変えられないので、間違ったまま端末に入れてしまう前にここで落とす。
//
// 特に VITE_API_BASE_URL は、未設定だと相対パスの "/api" になり、アプリ内では
// capacitor://localhost/api（自分自身のバンドル）を叩いて必ず失敗する。
import { loadEnv } from "vite";

const mode = process.env.MODE || "production";
const env = loadEnv(mode, process.cwd(), "");

const problems = [];

const apiBase = env.VITE_API_BASE_URL?.trim();
if (!apiBase) {
  problems.push(
    "VITE_API_BASE_URL が未設定です。バックエンドの絶対 URL（末尾は /api）を指定してください。",
  );
} else if (!/^https:\/\//i.test(apiBase)) {
  problems.push(
    `VITE_API_BASE_URL が https で始まっていません: ${apiBase}\n` +
      "  iOS は App Transport Security で平文 HTTP を拒否します。",
  );
}

if (!env.VITE_SUPABASE_URL?.trim() || !env.VITE_SUPABASE_ANON_KEY?.trim()) {
  problems.push(
    "VITE_SUPABASE_URL と VITE_SUPABASE_ANON_KEY が必要です。" +
      "未設定のままビルドすると、アプリは「初期設定が必要です」の画面しか出ません。",
  );
}

if (problems.length) {
  process.stderr.write(
    `\niOS 向けビルドの設定が足りません（mode=${mode}）:\n\n` +
      problems.map((line) => `  - ${line}`).join("\n") +
      "\n\nfrontend/.env.production に設定してください（雛形は frontend/.env.example）。\n\n",
  );
  process.exit(1);
}

process.stdout.write(`iOS build env OK (mode=${mode}, API=${apiBase})\n`);
