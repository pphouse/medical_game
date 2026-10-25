import { createClient } from "@supabase/supabase-js";
import { isNative, nativeStorage } from "../native";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

// ネイティブ（iOS アプリ）はブラウザと事情が違う:
//  - セッションは OS 側の永続領域に置く（native.js のコメント参照）
//  - メールのリンクはカスタムスキームで「アプリを開き直す」形で届くので、
//    起動時の URL を見る detectSessionInUrl は効かない。deepLink.js が拾う。
//  - トークンが URL フラグメントに載らない PKCE を使う。
const authOptions = isNative
  ? {
      storage: nativeStorage,
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: false,
      flowType: "pkce",
    }
  : undefined;

// null when the project env vars are missing — App shows a setup notice
// instead of crashing, so the repo can be opened before wiring Supabase.
export const supabase =
  url && anonKey ? createClient(url, anonKey, authOptions ? { auth: authOptions } : {}) : null;

export const isSupabaseConfigured = Boolean(supabase);

// パスワード再設定メールのリンクから戻ると PASSWORD_RECOVERY が届く。届いた
// 時点ではまだ画面が出来ていないことがある（Web は起動直後の URL 処理で
// 発火する）ので、ここで覚えておき、App の RecoveryRedirect が拾って
// 新しいパスワードの入力画面へ送る。
export const RECOVERY_EVENT = "medquiz:password-recovery";
let recoveryPending = false;

export function isRecoveryPending() {
  return recoveryPending;
}

export function clearRecoveryPending() {
  recoveryPending = false;
}

supabase?.auth.onAuthStateChange((event) => {
  if (event !== "PASSWORD_RECOVERY") return;
  recoveryPending = true;
  window.dispatchEvent(new Event(RECOVERY_EVENT));
});
