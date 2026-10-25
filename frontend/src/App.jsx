import { useEffect } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import BottomNav from "./components/BottomNav";
import MyPage from "./components/MyPage";
import QuestionPicker from "./components/QuestionPicker";
import ReviewDeck from "./components/ReviewDeck";
import { ProfileProvider } from "./context/ProfileContext";
import { useSession } from "./hooks/useSession";
import { isRecoveryPending, RECOVERY_EVENT } from "./lib/supabase";
import AdminDashboard from "./routes/Admin/Dashboard";
import AdminLayout from "./routes/Admin/Layout";
import AdminQuestionEdit from "./routes/Admin/QuestionEdit";
import AdminQuestions from "./routes/Admin/Questions";
import AdminReports from "./routes/Admin/Reports";
import AdminUsers from "./routes/Admin/Users";
import Auth from "./routes/Auth";
import Lobby from "./routes/Battle/Lobby";
import BattleRoom from "./routes/Battle/Room";
import MyQuestions from "./routes/Create/MyQuestions";
import QuestionForm from "./routes/Create/QuestionForm";
import ExamList from "./routes/Exams/List";
import ExamResult from "./routes/Exams/Result";
import ExamSession from "./routes/Exams/Session";
import QuizSession from "./routes/QuizSession";
import Privacy from "./routes/Privacy";
import Sources from "./routes/Sources";
import Ranking from "./routes/Ranking";
import ResetPassword from "./routes/ResetPassword";
import Solo from "./routes/Solo";
import Verify from "./routes/Verify";
import { STUDENT_VERIFICATION_ENABLED } from "./features";
import "./App.css";

/** Auth guard: everything below requires a Supabase session. */
function Protected() {
  const session = useSession();
  if (session === undefined) {
    return (
      <div className="screen">
        <p>読み込み中...</p>
      </div>
    );
  }
  if (!session) return <Navigate to="/auth" replace />;
  return (
    <ProfileProvider>
      <Outlet />
    </ProfileProvider>
  );
}

/** Layout for the main tabs (adds the bottom navigation bar). */
function TabShell() {
  return (
    <div className="app-shell with-bottom-nav">
      <Outlet />
      <BottomNav />
    </div>
  );
}

/** Layout for full-screen flows (question picker, quiz session). */
function FullScreenShell() {
  return (
    <div className="app-shell">
      <Outlet />
    </div>
  );
}

/** パスワード再設定のリンクから戻ってきたら、新しいパスワードの入力画面へ送る。 */
function RecoveryRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    const go = () => navigate("/reset-password", { replace: true });
    if (isRecoveryPending()) go();
    window.addEventListener(RECOVERY_EVENT, go);
    return () => window.removeEventListener(RECOVERY_EVENT, go);
  }, [navigate]);
  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <RecoveryRedirect />
      <Routes>
        <Route path="/auth" element={<Auth />} />
        {/* ログイン前でも読めるようにしておく。App Store Connect に
            登録する URL であり、審査担当者も未ログインで開く。 */}
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route element={<Protected />}>
          <Route element={<TabShell />}>
            <Route path="/" element={<Solo />} />
            <Route path="/solo" element={<Solo />} />
            <Route path="/review" element={<ReviewDeck />} />
            <Route path="/battle" element={<Lobby />} />
            {/* 対戦中・対戦後も他のメニューへ移動できるよう、下部ナビのある
                シェルに置く（離脱すると同ランクのAIが代役として入る）。 */}
            <Route path="/battle/:code" element={<BattleRoom />} />
            <Route path="/exams" element={<ExamList />} />
            <Route path="/ranking" element={<Ranking />} />
            {STUDENT_VERIFICATION_ENABLED && (
              <Route path="/create" element={<MyQuestions />} />
            )}
            <Route path="/mypage" element={<MyPage />} />
            {STUDENT_VERIFICATION_ENABLED && (
              <Route path="/settings/verification" element={<Verify />} />
            )}
          </Route>
          <Route element={<FullScreenShell />}>
            {/* 管理画面。ガードは AdminLayout 側（サーバでも IsModerator で守る）。 */}
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<AdminDashboard />} />
              <Route path="questions" element={<AdminQuestions />} />
              <Route path="reports" element={<AdminReports />} />
              <Route path="users" element={<AdminUsers />} />
            </Route>
            <Route path="/admin/questions/new" element={<AdminQuestionEdit />} />
            <Route path="/admin/questions/:questionId" element={<AdminQuestionEdit />} />
            <Route path="/solo/:category" element={<QuestionPicker />} />
            {STUDENT_VERIFICATION_ENABLED && (
              <Route path="/create/new" element={<QuestionForm />} />
            )}
            {STUDENT_VERIFICATION_ENABLED && (
              <Route path="/create/:questionId/edit" element={<QuestionForm />} />
            )}
            <Route path="/quiz" element={<QuizSession />} />
            <Route path="/exams/:examId" element={<ExamSession />} />
            <Route path="/exams/:examId/result" element={<ExamResult />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
