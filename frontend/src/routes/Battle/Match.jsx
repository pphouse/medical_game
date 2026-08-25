import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import TierBadge from "../../components/TierBadge";

/** 上部に常時出るVSヘッダー。自分と相手の名前・大学・ランク・HPを見せる。 */
function VersusHeader({ me, opponent, damageFor }) {
  return (
    <div className="vs-header">
      <Fighter side="me" p={me} damage={damageFor(me)} />
      <span className="vs-badge">VS</span>
      <Fighter side="opponent" p={opponent} damage={damageFor(opponent)} />
    </div>
  );
}

function Fighter({ side, p, damage }) {
  if (!p) return <div className={`fighter fighter-${side}`} />;
  const hp = Math.max(0, p.hp ?? 0);
  const state = hp <= 30 ? " danger" : hp <= 60 ? " warn" : "";
  return (
    <div className={`fighter fighter-${side}${damage ? " hit" : ""}`}>
      <div className="fighter-id">
        <span className="fighter-name">{p.display_name}</span>
        <span className="fighter-univ">{p.university ?? "所属未設定"}</span>
      </div>
      <div className="fighter-hp-row">
        <TierBadge tier={p.tier} fallback="―" />
        <div className="hp-bar">
          <div className={`hp-fill${state}`} style={{ width: `${hp}%` }} />
        </div>
        <span className="hp-value">{hp}%</span>
      </div>
      {damage > 0 && <span className="damage-pop">-{damage}%</span>}
    </div>
  );
}

/** 対戦開始前のVS演出。 */
function VersusIntro({ me, opponent }) {
  return (
    <div className="vs-intro">
      <div className="vs-intro-inner">
        <div className="vs-intro-side vs-intro-left">
          <span className="vs-intro-name">{me?.display_name}</span>
          <span className="vs-intro-univ">{me?.university ?? ""}</span>
          <TierBadge tier={me?.tier} fallback="―" large />
        </div>
        <span className="vs-intro-vs">VS</span>
        <div className="vs-intro-side vs-intro-right">
          <span className="vs-intro-name">{opponent?.display_name}</span>
          <span className="vs-intro-univ">{opponent?.university ?? ""}</span>
          <TierBadge tier={opponent?.tier} fallback="―" large />
        </div>
      </div>
      <p className="vs-intro-go">BATTLE START!</p>
    </div>
  );
}

/** 出題 + 選択 + 回答ボタン。状態は親 (Room) がポーリングで供給する。 */
export default function Match({ state, refresh, onLeave }) {
  const { round, participants, last_result: lastResult } = state;
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);
  const [remaining, setRemaining] = useState(null);
  const [flash, setFlash] = useState(null);
  const [intro, setIntro] = useState(true);
  const seenRoundRef = useRef(null);
  const seenResultRef = useRef(null);

  const me = participants.find((p) => p.is_me);
  const opponent = participants.find((p) => !p.is_me);

  // 開幕のVS演出は最初の数秒だけ
  useEffect(() => {
    const t = setTimeout(() => setIntro(false), 2200);
    return () => clearTimeout(t);
  }, []);

  // ラウンドが変わったら選択をリセット
  useEffect(() => {
    if (round?.id && seenRoundRef.current !== round.id) {
      seenRoundRef.current = round.id;
      setSelected(null);
    }
  }, [round?.id]);

  // 被弾／攻撃成功のフラッシュ演出
  useEffect(() => {
    if (!lastResult) return;
    const key = `${lastResult.number}`;
    if (seenResultRef.current === key) return;
    seenResultRef.current = key;
    const myDamage = lastResult.my_damage ?? 0;
    if (myDamage > 0) setFlash("hit");
    else if (lastResult.reason === "wrong_answer" || lastResult.reason === "slower_answer") {
      setFlash("attack");
    }
    const t = setTimeout(() => setFlash(null), 900);
    return () => clearTimeout(t);
  }, [lastResult]);

  useEffect(() => {
    if (!round?.closes_at) return undefined;
    const tick = () => {
      const ms = new Date(round.closes_at).getTime() - Date.now();
      setRemaining(Math.max(0, Math.ceil(ms / 1000)));
    };
    tick();
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  }, [round?.closes_at]);

  const damageFor = (p) =>
    p && lastResult?.damage ? Number(lastResult.damage[p.profile_id] ?? 0) : 0;

  async function handleAnswer() {
    if (!selected) return;
    setBusy(true);
    try {
      await api.battleAnswer(round.id, selected);
      await refresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleLeave() {
    if (
      !window.confirm(
        "対戦から退出しますか？ここまでのHPで確定し、相手には自動で代わりのプレイヤーが入ります。"
      )
    ) {
      return;
    }
    await onLeave();
  }

  if (intro) return <VersusIntro me={me} opponent={opponent} />;

  if (!round) {
    return (
      <div className="screen battle-screen">
        <VersusHeader me={me} opponent={opponent} damageFor={damageFor} />
        <p>次のラウンドを待っています…</p>
      </div>
    );
  }

  const question = round.question;
  const answered = round.i_have_answered;
  const opponentAnswered =
    opponent && round.answered_profile_ids?.includes(opponent.profile_id);

  return (
    <div className={`screen battle-screen${flash ? ` flash-${flash}` : ""}`}>
      <VersusHeader me={me} opponent={opponent} damageFor={damageFor} />

      <div className="battle-roundbar">
        <span className="battle-round-no">
          Q{round.number}
          <span className="battle-round-total">/{round.total}</span>
        </span>
        <span className={`battle-timer${remaining !== null && remaining <= 5 ? " urgent" : ""}`}>
          {remaining ?? "--"}
        </span>
        <button className="battle-leave-button" onClick={handleLeave}>
          退出
        </button>
      </div>

      {lastResult && lastResult.number === round.number - 1 && (
        <div className="battle-last-result">
          前問の正解: <b>{lastResult.correct_choice_key}</b>
          {lastResult.reason === "all_wrong" && "（両者不正解）"}
          {lastResult.reason === "draw" && "（引き分け）"}
        </div>
      )}

      <div className="question-card battle-question-card">
        {question.case_stem && <p className="case-stem">{question.case_stem}</p>}
        <p className="question-text">{question.question_text}</p>

        <div className="choices">
          {question.choices.map((choice) => (
            <button
              key={choice.key}
              className={`choice battle-choice${selected === choice.key ? " selected" : ""}`}
              disabled={answered || busy}
              onClick={() => setSelected(choice.key)}
            >
              <span className="choice-key">{choice.key}</span>
              <span>{choice.text}</span>
            </button>
          ))}
        </div>

        {answered ? (
          <p className="battle-waiting">
            {opponentAnswered ? "判定中…" : "相手の回答を待っています…"}
          </p>
        ) : (
          <button
            className="cta-button battle-answer-button"
            disabled={!selected || busy}
            onClick={handleAnswer}
          >
            {selected ? `${selected} で回答する` : "選択肢を選んでください"}
          </button>
        )}

        {opponentAnswered && !answered && (
          <p className="battle-opponent-ready">相手は回答済み！急いで！</p>
        )}
      </div>
    </div>
  );
}
