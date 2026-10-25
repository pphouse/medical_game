import { useState } from "react";
import { supabase } from "../lib/supabase";
import { LEGAL_DOCS, TERMS_VERSION } from "./documents";
import LegalModal from "./LegalModal";

/** 同意済みか。同意の記録は Supabase のユーザー情報（user_metadata）に置く。
 * 端末ではなくアカウントに付くので、機種変更や Web 版でも聞き直さない。 */
export function hasAgreed(session) {
  return session?.user?.user_metadata?.agreed_terms_version === TERMS_VERSION;
}

/** 初回ログイン時（と規約を改めたとき）に出す同意画面。
 * 出典・免責は毎回の解説に大きく出すと邪魔なので、ここで一度読んでもらう。 */
export default function Consent() {
  const [open, setOpen] = useState(null);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleAgree() {
    setBusy(true);
    setError(null);
    try {
      // 更新が届くと onAuthStateChange（USER_UPDATED）でセッションが差し替わり、
      // Protected が同意済みとして本来の画面を出す。
      const { error: err } = await supabase.auth.updateUser({
        data: { agreed_terms_version: TERMS_VERSION, agreed_at: new Date().toISOString() },
      });
      if (err) throw err;
    } catch (err) {
      setError(err.message ?? String(err));
      setBusy(false);
    }
  }

  async function handleDecline() {
    await supabase.auth.signOut();
  }

  return (
    <div className="screen consent-screen">
      <div className="auth-card consent-card">
        <h1 className="consent-title">医トレへようこそ！</h1>
        <p className="consent-lead">
          {"医トレは、医学生のための CBT・医師国家試験の問題演習アプリです。" +
            "ご利用には以下の各文書への同意が必要です。"}
          <br />
          （各文書名をタップすると全文が表示されます）
        </p>
        <div className="consent-docs">
          {LEGAL_DOCS.map((doc) => (
            <button
              key={doc.key}
              type="button"
              className="consent-doc"
              onClick={() => setOpen(doc.key)}
            >
              {doc.title}
            </button>
          ))}
        </div>
        <label className="consent-check">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
          />
          <span>上記すべての文書を確認の上、同意します。</span>
        </label>
        {error && <p className="error">{error}</p>}
        <button
          type="button"
          className="cta-button"
          disabled={!checked || busy}
          onClick={handleAgree}
        >
          {busy ? "処理中..." : "同意してはじめる"}
        </button>
        <button type="button" className="auth-magic-link" onClick={handleDecline}>
          同意しない（ログアウト）
        </button>
      </div>
      {open && <LegalModal docKey={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
