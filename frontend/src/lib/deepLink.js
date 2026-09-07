import { supabase } from "./supabase";

/**
 * カスタムスキームで開き直された URL から、クエリとフラグメントの両方を拾う。
 * Supabase はフロー（PKCE / implicit）によってどちらに載せるかが違うので、
 * 片方だけを見ると「リンクを踏んだのにログインできない」になる。
 */
export function callbackParams(rawUrl) {
  const [beforeHash, ...hashParts] = String(rawUrl).split("#");
  const hash = hashParts.join("#");
  const q = beforeHash.indexOf("?");
  const query = q === -1 ? "" : beforeHash.slice(q + 1);
  const joined = [query, hash].filter(Boolean).join("&");
  return new URLSearchParams(joined);
}

/**
 * メール（マジックリンク・登録確認）から戻ってきた URL でログインを完了させる。
 * 認証情報が載っていない URL なら false を返すだけで、何もしない。
 */
export async function completeAuthFromUrl(rawUrl) {
  if (!supabase) return false;
  const params = callbackParams(rawUrl);

  const failure = params.get("error_description") || params.get("error");
  if (failure) throw new Error(failure);

  const code = params.get("code");
  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) throw error;
    return true;
  }

  const accessToken = params.get("access_token");
  const refreshToken = params.get("refresh_token");
  if (accessToken && refreshToken) {
    const { error } = await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
    if (error) throw error;
    return true;
  }

  return false;
}
