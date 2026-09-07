import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";

/** true only inside the packaged iOS/Android shell — false in every browser. */
export const isNative = Capacitor.isNativePlatform();

/** "ios" | "android" | "web" */
export const platform = Capacitor.getPlatform();

/**
 * アプリを開き直すためのカスタム URL スキーム。
 * ios/App/App/Info.plist の CFBundleURLTypes と、Supabase の
 * Authentication → URL Configuration → Redirect URLs の両方に、
 * まったく同じ文字列が登録されていないとメールのリンクが戻ってこない。
 */
export const DEEP_LINK_SCHEME = "jp.pphouse.medquiz";
export const AUTH_CALLBACK_URL = `${DEEP_LINK_SCHEME}://auth-callback`;

/** メール内のリンクから戻ってくる先。Web は自分のオリジン、アプリはスキーム。 */
export function authRedirectUrl() {
  return isNative ? AUTH_CALLBACK_URL : window.location.origin;
}

/**
 * Supabase のセッション保存先。WKWebView の localStorage は OS の
 * ストレージ整理で消えることがあり、消えると「勝手にログアウトされる」ので、
 * ネイティブでは OS 側の永続領域（iOS は UserDefaults）に置く。
 */
export const nativeStorage = {
  getItem: async (key) => (await Preferences.get({ key })).value,
  setItem: async (key, value) => {
    await Preferences.set({ key, value });
  },
  removeItem: async (key) => {
    await Preferences.remove({ key });
  },
};
