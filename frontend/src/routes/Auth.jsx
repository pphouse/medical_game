import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { isSupabaseConfigured, supabase } from "../lib/supabase";

export default function Auth() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [notice, setNotice] = useState(
    params.get("reason") === "expired"
      ? "ログインの有効期限が切れました。もう一度ログインしてください。"
      : null
  );
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (!isSupabaseConfigured) {
    return (
      <div className="screen">
        <h2>初期設定が必要です</h2>
        <div className="empty-card">
          Supabase プロジェクトが設定されていません。frontend/.env.local に
          VITE_SUPABASE_URL と VITE_SUPABASE_ANON_KEY を設定してください
          （手順は docs/supabase-setup.md）。
        </div>
      </div>
    );
  }

  async function afterSignIn() {
    // Ensure the API-side Profile exists, seeding display_name on signup.
    await api.bootstrap(displayName ? { display_name: displayName } : {});
    navigate("/", { replace: true });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "signup") {
        const { data, error: err } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { display_name: displayName } },
        });
        if (err) throw err;
        if (data.session) {
          await afterSignIn();
        } else {
          setNotice("確認メールを送信しました。メール内のリンクを開いてから、ログインしてください。");
          setMode("login");
        }
      } else {
        const { error: err } = await supabase.auth.signInWithPassword({ email, password });
        if (err) throw err;
        await afterSignIn();
      }
    } catch (err) {
      setError(err.message ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleMagicLink() {
    if (!email) {
      setError("メールアドレスを入力してください。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: window.location.origin },
      });
      if (err) throw err;
      setNotice("ログイン用リンクをメールで送信しました。");
    } catch (err) {
      setError(err.message ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen auth-screen">
      <div className="home-header">
        <h1>
          <span className="title-main">CBT・国試対策クイズ</span>
          <span className="title-sub">AIが弱点を見抜く、あなただけの合格戦略。</span>
        </h1>
      </div>

      <div className="auth-card">
        <div className="auth-tabs">
          <button
            className={`auth-tab${mode === "login" ? " active" : ""}`}
            onClick={() => setMode("login")}
            type="button"
          >
            ログイン
          </button>
          <button
            className={`auth-tab${mode === "signup" ? " active" : ""}`}
            onClick={() => setMode("signup")}
            type="button"
          >
            新規登録
          </button>
        </div>

        {notice && <p className="auth-notice">{notice}</p>}
        {error && <p className="error">{error}</p>}

        <form onSubmit={handleSubmit} className="auth-form">
          {mode === "signup" && (
            <label className="auth-field">
              表示名（ランキング等に表示されます）
              <input
                type="text"
                value={displayName}
                maxLength={50}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="例: 医学太郎"
              />
            </label>
          )}
          <label className="auth-field">
            メールアドレス
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </label>
          <label className="auth-field">
            パスワード
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
            />
          </label>
          <button className="cta-button" disabled={busy} type="submit">
            {busy ? "処理中..." : mode === "signup" ? "登録する" : "ログイン"}
          </button>
        </form>

        <button className="auth-magic-link" onClick={handleMagicLink} disabled={busy} type="button">
          パスワードなしでログイン（Magic Link をメールで受け取る）
        </button>
      </div>
    </div>
  );
}
