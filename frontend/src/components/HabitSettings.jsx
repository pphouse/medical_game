import { useState } from "react";
import { api } from "../api";
import { useHabit } from "../hooks/useHabit";
import {
  REMINDER_ERRORS,
  disableReminders,
  enableReminders,
  remindersSupported,
  setReminderHour,
} from "../reminders";
import { GoalChips } from "./DailyGoalCard";

// 深夜・早朝には送らない。
const HOURS = Array.from({ length: 18 }, (_, i) => i + 6);

/** マイページの「目標とリマインド」。 */
export default function HabitSettings() {
  const { habit, setHabit, unavailable } = useHabit();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (unavailable) return null;
  if (!habit) {
    return (
      <div className="mypage-card">
        <p>読み込み中...</p>
      </div>
    );
  }

  const supported = remindersSupported();
  const { enabled, hour } = habit.reminder;

  async function run(action) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const chooseGoal = (n) => run(async () => setHabit(await api.setDailyGoal(n)));

  const toggle = () =>
    run(async () => {
      if (enabled) {
        setHabit(await disableReminders());
        return;
      }
      const result = await enableReminders(hour);
      if (result.ok) setHabit(result.habit);
      else setError(REMINDER_ERRORS[result.reason]);
    });

  const changeHour = (value) => run(async () => setHabit(await setReminderHour(value)));

  return (
    <div className="mypage-card habit-settings">
      <p className="habit-settings-label">1日の目標</p>
      <GoalChips
        choices={habit.goal_choices}
        value={habit.goal}
        disabled={busy}
        onSelect={chooseGoal}
      />
      {habit.upcoming_goal && (
        <p className="exam-meta">
          今日の目標はもう達成しているので、{habit.upcoming_goal.questions_per_day}問は明日からです。
        </p>
      )}

      <div className="habit-settings-row">
        <span className="habit-settings-label">リマインド</span>
        <button
          role="switch"
          aria-checked={enabled}
          aria-label="リマインド"
          className={`habit-switch${enabled ? " on" : ""}`}
          disabled={busy || !supported || habit.goal == null}
          onClick={toggle}
        >
          <span className="habit-switch-knob" />
        </button>
      </div>
      {habit.goal == null && <p className="exam-meta">先に1日の目標を決めてください。</p>}
      {!supported && <p className="exam-meta">{REMINDER_ERRORS.unsupported}</p>}

      <label className="habit-settings-row">
        <span className="habit-settings-label">時刻</span>
        <select
          className="habit-hour"
          value={hour}
          disabled={busy || !enabled}
          onChange={(e) => changeHour(Number(e.target.value))}
        >
          {HOURS.map((h) => (
            <option key={h} value={h}>
              {h}:00
            </option>
          ))}
        </select>
      </label>
      {enabled && habit.suggested_hour != null && habit.suggested_hour !== hour && (
        <p className="exam-meta">
          いつも{habit.suggested_hour}時ごろに解き始めています。
          <button
            className="habit-suggest"
            disabled={busy}
            onClick={() => changeHour(habit.suggested_hour)}
          >
            {habit.suggested_hour}時にする
          </button>
        </p>
      )}
      <p className="exam-meta">
        目標に届いた日は送りません。夜9時になってもまだなら、連続記録が途切れそうだとお知らせします。
        7日間解かなかった場合は、いったん止めます。
      </p>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
