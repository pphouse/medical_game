import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../hooks/useSession";
import { authErrorMessage } from "../lib/authErrors";
import { clearRecoveryPending, supabase } from "../lib/supabase";

/** パスワード再設定メールのリンクから来たときの、新しいパスワードの入力画面。
 * リンクを開いた時点で一時的にログイン済みになっているので、updateUser で
 * パスワードを書き換えるだけでよい。 */
export default function ResetPassword() {
  const navigate = useNavigate();
  const session = useSession();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== confirm) {
      setError("確認用のパスワードが一致しません。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await supabase.auth.updateUser({ password });
      if (err) throw err;
      clearRecoveryPending();
      navigate("/", { replace: true });
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (session === undefined) {
    return (
      <div className="screen">
        <p>読み込み中...</p>
      </div>
    );
  }

  return (
    <div className="screen auth-screen">
      <div className="auth-card">
        <h2>新しいパスワードの設定</h2>
        {!session ? (
          <>
            <p className="error">
              リンクの有効期限が切れたか、すでに使われています。もう一度、ログイン画面の「パスワードを忘れた方」からメールを送ってください。
            </p>
            <Link className="cta-button" to="/auth">
              ログイン画面へ
            </Link>
          </>
        ) : (
          <form onSubmit={handleSubmit} className="auth-form">
            {error && <p className="error">{error}</p>}
            <label className="auth-field">
              新しいパスワード（8文字以上）
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            <label className="auth-field">
              新しいパスワード（確認）
              <input
                type="password"
                required
                minLength={8}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            <button className="cta-button" disabled={busy} type="submit">
              {busy ? "処理中..." : "パスワードを変更する"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
