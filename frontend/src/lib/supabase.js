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
