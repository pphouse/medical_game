import { Navigate, useLocation, useNavigate } from "react-router-dom";
import QuizScreen from "../components/QuizScreen";

/** Wraps the (presentational) QuizScreen behind a URL. The question list
 * arrives via location.state from QuestionPicker / ReviewDeck; a direct
 * hit without state falls back to the top page.
 *
 * 戻るは履歴を1つ戻るのではなく、呼び出し元が指定した親の画面へ出る
 * （`backTo`）。履歴だと、戻った先からまたこの画面へ入れる作りのときに
 * 2画面を行き来するだけになって抜け出せない。 */
export default function QuizSession() {
  const { state } = useLocation();
  const navigate = useNavigate();

  if (!state?.questions) return <Navigate to="/" replace />;

  return (
    <QuizScreen
      title={state.title}
      kicker={state.kicker}
      questions={state.questions}
      startIndex={state.startIndex ?? 0}
      context={state.context ?? "solo"}
      backLabel={state.backLabel ?? "ホームへ"}
      onBack={() => navigate(state.backTo ?? "/")}
    />
  );
}
