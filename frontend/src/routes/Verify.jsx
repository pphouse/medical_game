import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useProfile } from "../context/ProfileContext";
import { supabase } from "../lib/supabase";

/** 学生証認証の申請画面 (spec フェーズ7).
 *
 * 画像は Django を経由せず、signed upload URL で Supabase Storage の
 * private バケットへ直接アップロードする。完了後に complete を呼んで
 * status=pending（審査待ち）にする。
 */
export default function Verify() {
  const navigate = useNavigate();
  const { profile, refresh } = useProfile();
  const [status, setStatus] = useState(null);
  const [universities, setUniversities] = useState([]);
  const [universityId, setUniversityId] = useState("");
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.verificationStatus().then(setStatus).catch((e) => setError(e.message));
    api.universities().then(setUniversities).catch(() => {});
  }, []);

  if (error && !status) return <p className="error">{error}</p>;
  if (!status) return <p>読み込み中...</p>;

  const latest = status.latest;
  const underReview = latest?.status === "pending";

  async function handleApply() {
    if (!universityId || !file) {
      setError("大学と学生証の画像を選択してください。");
      return;
    }
    if (!supabase) {
      setError("Supabase が設定されていないため、画像をアップロードできません。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { verification, upload } = await api.applyVerification(Number(universityId));
      const { error: uploadError } = await supabase.storage
        .from(upload.bucket)
        .uploadToSignedUrl(upload.path, upload.token, file, {
          contentType: file.type || "image/jpeg",
        });
      if (uploadError) {
        throw new Error(`画像のアップロードに失敗しました: ${uploadError.message}`);
      }
      await api.completeVerification(verification.id);
      const next = await api.verificationStatus();
      setStatus(next);
      refresh?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen">
      <button className="back-link" onClick={() => navigate(-1)}>
        ← 戻る
      </button>
      <h2>学生証認証</h2>

      {status.student_verified || profile?.student_verified ? (
        <div className="mypage-card verify-done">
          <p className="notification-title">✅ 学生証認証済みです</p>
          <p className="notification-desc">
            学内限定問題の閲覧と、自作問題の作成ができます。
          </p>
          <button className="cta-button" onClick={() => navigate("/create")}>
            問題をつくる
          </button>
        </div>
      ) : underReview ? (
        <div className="mypage-card">
          <p className="notification-title">⏳ 審査待ちです</p>
          <p className="notification-desc">
            {latest.university ?? "所属大学"}の学生証として{" "}
            {latest.submitted_at
              ? new Date(latest.submitted_at).toLocaleDateString("ja-JP")
              : ""}{" "}
            に申請されました。承認されるまでお待ちください。
          </p>
        </div>
      ) : (
        <>
          <div className="mypage-card">
            <p className="notification-desc">
              学生証の画像を提出すると、モデレーターの審査後に「学生証認証済み」
              となり、学内限定問題の閲覧・自作問題の作成ができるようになります。
              画像は審査のためだけに使われ、却下時は即時、承認後も90日で削除されます。
            </p>
          </div>

          {latest?.status === "rejected" && (
            <div className="mypage-card verify-rejected">
              <p className="notification-title">前回の申請は却下されました</p>
              <p className="notification-desc">
                理由: {latest.reject_reason || "（理由の記載なし）"}
              </p>
            </div>
          )}

          {error && <p className="error">{error}</p>}

          <div className="mypage-card create-form">
            <label className="auth-field">
              所属大学
              <select
                className="notification-select"
                value={universityId}
                onChange={(e) => setUniversityId(e.target.value)}
              >
                <option value="">選択してください</option>
                {universities.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="auth-field">
              学生証の画像（表面）
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>

            <button
              className="cta-button"
              onClick={handleApply}
              disabled={busy || !universityId || !file}
            >
              {busy ? "申請中..." : "認証を申請する"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
