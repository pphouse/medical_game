import { useState } from "react";
import { api } from "../api";

const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];
const STATUS_LABEL = {
  achieved: "達成",
  rest: "お休み",
  missed: "未達",
  today: "今日",
  none: "記録なし",
};

function parseDay(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function FlameIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M12.3 2.5c.9 3.1-1.3 5-2.8 6.8C8 11.1 7 12.8 7 15a5 5 0 0 0 10 0c0-2.3-1-3.9-2.1-5 0 1.5-.6 2.6-1.6 3.2.4-3.5-.2-7.4-1-10.7Z"
        fill="currentColor"
      />
    </svg>
  );
}

/** 目標の問題数を選ぶチップ。ホームのカードとマイページで共通。 */
export function GoalChips({ choices, value, disabled, onSelect }) {
  return (
    <div className="filter-chip-row goal-chips" role="group" aria-label="1日の目標">
      {choices.map((n) => (
        <button
          key={n}
          className={`filter-chip${value === n ? " active" : ""}`}
          aria-pressed={value === n}
          disabled={disabled}
          onClick={() => onSelect(n)}
        >
          {n}問
        </button>
      ))}
    </div>
  );
}

function GoalRing({ count, goal, achieved }) {
  const radius = 24;
  const circumference = 2 * Math.PI * radius;
  const ratio = Math.min(count / goal, 1);
  return (
    <div className={`goal-ring${achieved ? " done" : ""}`}>
      <svg viewBox="0 0 60 60" aria-hidden="true">
        <circle cx="30" cy="30" r={radius} className="goal-ring-track" />
        <circle
          cx="30"
          cy="30"
          r={radius}
          className="goal-ring-fill"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
          transform="rotate(-90 30 30)"
        />
      </svg>
      <span className="goal-ring-text">{achieved ? "✓" : `${count}/${goal}`}</span>
    </div>
  );
}

/** 直近7日。達成・お休み（週1日まで記録を守った日）・未達を並べる。 */
export function WeekStrip({ days }) {
  return (
    <ol className="goal-week" aria-label="この1週間">
      {days.map((day) => {
        const date = parseDay(day.date);
        return (
          <li
            key={day.date}
            className={`goal-day ${day.status}`}
            aria-label={`${date.getMonth() + 1}月${date.getDate()}日: ${STATUS_LABEL[day.status]}`}
          >
            <span className="goal-day-label">{WEEKDAYS[date.getDay()]}</span>
            <span className="goal-day-dot">
              {day.status === "achieved" ? "✓" : day.status === "rest" ? "休" : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** ホームの「今日の目標」。目標が無ければ、決めるところから始める。 */
export default function DailyGoalCard({ habit, onChange }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  if (!habit) return null;

  async function choose(n) {
    setSaving(true);
    setError(null);
    try {
      onChange(await api.setDailyGoal(n));
      setEditing(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (habit.goal == null || editing) {
    return (
      <section className="goal-card goal-card-setup" aria-label="1日の目標">
        <h2 className="goal-card-title">
          {habit.goal == null ? "1日の目標を決めよう" : "1日の目標を変える"}
        </h2>
        <p className="goal-card-note">
          決めた問題数を毎日解くと、連続記録が伸びます。届かない日も、週に1日まではお休みにできます。
        </p>
        <GoalChips
          choices={habit.goal_choices}
          value={habit.goal}
          disabled={saving}
          onSelect={choose}
        />
        {editing && (
          <button className="goal-card-link" onClick={() => setEditing(false)}>
            変えずに戻る
          </button>
        )}
        {error && <p className="error">{error}</p>}
      </section>
    );
  }

  return (
    <section className={`goal-card${habit.achieved ? " achieved" : ""}`} aria-label="今日の目標">
      <div className="goal-card-top">
        <GoalRing count={habit.count} goal={habit.goal} achieved={habit.achieved} />
        <div className="goal-card-body">
          <p className="goal-card-headline">
            {habit.achieved ? "今日の目標を達成！" : `あと${habit.remaining}問`}
          </p>
          <p className="goal-card-sub">
            今日 {habit.count}/{habit.goal}問
            {habit.upcoming_goal ? `・明日から${habit.upcoming_goal.questions_per_day}問` : ""}
          </p>
        </div>
        <div className="goal-streak" aria-label={`${habit.streak}日連続`}>
          <FlameIcon />
          <span className="goal-streak-value">{habit.streak}</span>
          <span className="goal-streak-unit">日連続</span>
        </div>
      </div>
      <WeekStrip days={habit.days} />
      <button className="goal-card-link" onClick={() => setEditing(true)}>
        目標を変える（今は{habit.goal}問）
      </button>
    </section>
  );
}
