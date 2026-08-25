import { useEffect, useState } from "react";
import { api } from "../../api";
import { supabase } from "../../lib/supabase";

/** 出題 + 早押しボタン + 回答。状態は親 (Room) がポーリングで供給する。 */
export default function Match({ state, refresh, onLeave }) {
  const { round, participants, last_result: lastResult } = state;
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState(null);

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

  if (!round) {
    return (
      <div className="screen">
        <p>次のラウンドを待っています…</p>
      </div>
    );
  }

  async function handleBuzz() {
    setBusy(true);
    try {
      // 早押しは Supabase RPC (サーバ時刻 clock_timestamp で順位確定) を
      // 優先し、未設定環境では Django フォールバックを使う (spec 4-1)
      if (supabase) {
        const { error } = await supabase.rpc("claim_buzz", { p_round_id: round.id });
        if (error) throw new Error(error.message);
      } else {
        await api.battleBuzz(round.id);
      }
      await refresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAnswer(key) {
    setBusy(true);
    try {
      await api.battleAnswer(round.id, key);
      await refresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  }

  const question = round.question;

  async function handleLeave() {
    if (!window.confirm("対戦から退出しますか？ここまでのスコアで確定し、相手には自動でAIが代わりに入ります。")) {
      return;
    }
    await onLeave();
  }

  return (
    <div className="screen">
      <div className="quiz-topbar">
        <span className="quiz-topbar-title">
          第{round.number}問 / {round.total}
        </span>
        <span className="progress">残り {remaining ?? "--"} 秒</span>
        <button className="battle-leave-button" onClick={handleLeave}>
          退出する
        </button>
      </div>

      <div className="battle-scorebar">
        {participants.map((p) => (
          <span key={p.display_name} className={`battle-score${p.is_me ? " me" : ""}`}>
            {p.display_name}: <strong>{p.score}</strong>
          </span>
        ))}
      </div>

      {lastResult && lastResult.number === round.number - 1 && (
        <div className="battle-last-result">
          前問の正解: {lastResult.correct_choice_key}
          {lastResult.winner ? `（${lastResult.winner} が正解）` : "（正解者なし）"}
        </div>
      )}

      <div className="question-card">
        {question.case_stem && <p className="case-stem">{question.case_stem}</p>}
        <p className="question-text">{question.question_text}</p>

        <div className="choices">
          {question.choices.map((choice) => (
            <button
              key={choice.key}
              className="choice"
              disabled={!round.i_am_answering || busy}
              onClick={() => handleAnswer(choice.key)}
            >
              <span className="choice-key">{choice.key}</span>
              <span>{choice.text}</span>
            </button>
          ))}
        </div>

        {round.can_buzz ? (
          <button className="buzz-button" onClick={handleBuzz} disabled={busy}>
            早押し！
          </button>
        ) : round.i_am_answering ? (
          <p className="battle-answering">回答権があります。選択肢を選んでください！</p>
        ) : (
          <p className="battle-waiting">
            {round.answering_rank
              ? `${round.answering_rank}位の回答を待っています…`
              : "みんなの早押しを待っています…"}
          </p>
        )}

        {round.buzzes.length > 0 && (
          <div className="battle-buzz-list">
            {round.buzzes.map((b) => (
              <span
                key={b.rank}
                className={`battle-buzz-chip${b.is_correct === false ? " wrong" : ""}${
                  b.is_correct === true ? " right" : ""
                }`}
              >
                {b.rank}. {b.display_name}
                {b.is_me && "（あなた）"}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
