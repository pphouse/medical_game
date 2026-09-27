import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { syncReminders } from "../reminders";

/**
 * 今日の目標・進み具合・連続記録（/habits/today/）。
 *
 * 取れないとき（本番で表を作る前にデプロイされた等）は unavailable にして、
 * 呼び出し側は目標の表示ごと出さない。iOS アプリでは、新しい状態を受け取る
 * たびに端末の通知の予約も作り直す（ブラウザでは何もしない）。
 */
export function useHabit() {
  const [habit, setHabitState] = useState(null);
  const [unavailable, setUnavailable] = useState(false);

  const setHabit = useCallback((next) => {
    setHabitState(next);
    syncReminders(next);
  }, []);

  const reload = useCallback(async () => {
    try {
      const next = await api.habitToday();
      setHabit(next);
      setUnavailable(false);
      return next;
    } catch {
      setUnavailable(true);
      return null;
    }
  }, [setHabit]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { habit, setHabit, reload, unavailable };
}
