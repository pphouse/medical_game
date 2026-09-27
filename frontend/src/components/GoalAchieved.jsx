import { FlameIcon } from "./DailyGoalCard";

/** 解答中に今日の目標に届いた瞬間のお祝い。1日1回だけ出る（サーバの just_achieved）。 */
export default function GoalAchieved({ progress, onClose }) {
  return (
    <div className="goal-achieved" role="dialog" aria-modal="true" aria-labelledby="goal-achieved-title">
      <div className="goal-achieved-card">
        <div className="goal-achieved-flame">
          <FlameIcon />
        </div>
        <h2 id="goal-achieved-title">今日の目標を達成！</h2>
        <p>
          {progress.goal}問クリア。
          {progress.streak ? `${progress.streak}日連続です。` : ""}
        </p>
        <button className="cta-button" onClick={onClose} autoFocus>
          続ける
        </button>
      </div>
    </div>
  );
}
