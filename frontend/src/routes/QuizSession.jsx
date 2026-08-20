import { Navigate, useLocation, useNavigate } from "react-router-dom";
import QuizScreen from "../components/QuizScreen";

/** Wraps the (presentational) QuizScreen behind a URL. The question list
 * arrives via location.state from QuestionPicker / ReviewDeck; a direct
 * hit without state falls back to the top page. */
export default function QuizSession() {
  const { state } = useLocation();
  const navigate = useNavigate();

  if (!state?.questions) return <Navigate to="/" replace />;

  return (
    <QuizScreen
      title={state.title}
      questions={state.questions}
      startIndex={state.startIndex ?? 0}
      onBack={() => navigate(state.backTo ?? -1)}
    />
  );
}
