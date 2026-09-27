import { isNative } from "./native";

/** 起動画面を消す。ここで失敗するとアプリが起動画面のまま固まって見える。 */
async function hideSplash() {
  try {
    const { SplashScreen } = await import("@capacitor/splash-screen");
    await SplashScreen.hide();
  } catch {
    // capacitor.config.json の launchAutoHide が保険になっているので、
    // ここで消せなくても数秒後には勝手に消える。
  }
}

async function setUp() {
  const [{ App }, { Browser }, { Style, StatusBar }, { completeAuthFromUrl }] = await Promise.all([
    import("@capacitor/app"),
    import("@capacitor/browser"),
    import("@capacitor/status-bar"),
    import("./lib/deepLink"),
  ]);

  // Style.Default = 端末のライト/ダーク設定に追従する。アプリの配色も
  // prefers-color-scheme で切り替わるので、これで文字が背景に溶けない。
  await StatusBar.setStyle({ style: Style.Default }).catch(() => {});

  // 同じ URL が「起動時の URL」と appUrlOpen の両方で届くことがある。
  const seen = new Set();
  const handleUrl = async (url) => {
    if (!url || seen.has(url)) return;
    seen.add(url);
    try {
      await completeAuthFromUrl(url);
    } catch (err) {
      // 握りつぶすと「メールのリンクを踏んだのに無反応」になる。理由を
      // ログイン画面に渡して表示する。
      const reason = encodeURIComponent(err?.message ?? String(err));
      window.location.assign(`/auth?authError=${reason}`);
    }
  };

  App.addListener("appUrlOpen", ({ url }) => handleUrl(url));
  await App.getLaunchUrl()
    .then((launch) => handleUrl(launch?.url))
    .catch(() => {});

  // 外部サイト（出典の公表ページなど）をアプリの WebView で開くと、戻る手段が
  // なくなって詰む。閉じるボタンのある in-app ブラウザに逃がす。
  document.addEventListener("click", (event) => {
    const anchor = event.target?.closest?.("a[href]");
    if (!anchor) return;
    const href = anchor.getAttribute("href") ?? "";
    if (!/^https?:\/\//i.test(href)) return;
    event.preventDefault();
    Browser.open({ url: href }).catch(() => {});
  });
}

/**
 * ネイティブ（iOS アプリ）でだけ必要な起動処理。
 *
 * Capacitor のプラグインはブラウザ用の実装を持たないものがあるので、動的
 * import にして Web のバンドルから切り離す。Web では何もせずに返る。
 */
export async function initNative() {
  if (!isNative) return;
  try {
    await setUp();
  } finally {
    await hideSplash();
  }
}
