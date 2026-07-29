import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { disablePush, enablePush, pushSupported } from "../push";

const HOURS = Array.from({ length: 24 }, (_, h) => h);

export default function NotificationSettings() {
  const navigate = useNavigate();
  const [pref, setPref] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.notificationPreference().then(setPref).catch((e) => setError(e.message));
    api.reviewSummary().then(setSummary).catch(() => {});
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!pref) return <p>読み込み中...</p>;

  async function toggleEnabled() {
    setBusy(true);
    setError(null);
    try {
      if (!pref.enabled) {
        await enablePush(pref.vapid_public_key);
        const next = await api.updateNotificationPreference({ enabled: true });
        setPref(next);
      } else {
        await disablePush();
        const next = await api.updateNotificationPreference({ enabled: false });
        setPref(next);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function changeHour(e) {
    const next = await api.updateNotificationPreference({
      preferred_hour: Number(e.target.value),
    });
    setPref(next);
  }

  return (
    <div className="screen">
      <button className="back-link" onClick={() => navigate(-1)}>
        ← 戻る
      </button>
      <h2>復習リマインド設定</h2>

      {summary && (
        <div className="mypage-card">
          <p style={{ margin: 0 }}>
            復習期限: いま <strong>{summary.due_now}</strong>問 ／ 今日{" "}
            <strong>{summary.today}</strong>問 ／ 明日 <strong>{summary.tomorrow}</strong>問 ／
            今週 <strong>{summary.this_week}</strong>問
          </p>
        </div>
      )}

      <div className="mypage-card notification-card">
        <div className="notification-row">
          <div>
            <p className="notification-title">プッシュ通知</p>
            <p className="notification-desc">
              復習期限の問題が5問以上たまった日に、1日1回通知します（初期設定はオフ）。
            </p>
          </div>
          <button
            className={`notification-toggle${pref.enabled ? " on" : ""}`}
            onClick={toggleEnabled}
            disabled={busy || !pushSupported()}
            aria-pressed={pref.enabled}
          >
            {pref.enabled ? "オン" : "オフ"}
          </button>
        </div>
        {!pushSupported() && (
          <p className="notification-desc error">このブラウザは Web Push に対応していません。</p>
        )}

        <div className="notification-row">
          <p className="notification-title">通知時刻</p>
          <select value={pref.preferred_hour} onChange={changeHour} className="notification-select">
            {HOURS.map((h) => (
              <option key={h} value={h}>
                {h}:00
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
