import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import BottomNav from "./components/BottomNav";
import MyPage from "./components/MyPage";
import QuestionPicker from "./components/QuestionPicker";
import ReviewDeck from "./components/ReviewDeck";
import { ProfileProvider } from "./context/ProfileContext";
import { useSession } from "./hooks/useSession";
import Auth from "./routes/Auth";
import Lobby from "./routes/Battle/Lobby";
import BattleRoom from "./routes/Battle/Room";
import Menu from "./routes/Menu";
import Placeholder from "./routes/Placeholder";
import QuizSession from "./routes/QuizSession";
import Ranking from "./routes/Ranking";
import Solo from "./routes/Solo";
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

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route element={<Protected />}>
          <Route element={<TabShell />}>
            <Route path="/" element={<Menu />} />
            <Route path="/solo" element={<Solo />} />
            <Route path="/review" element={<ReviewDeck />} />
            <Route path="/battle" element={<Lobby />} />
            <Route path="/exams" element={<Placeholder title="模試" phase="フェーズ5" />} />
            <Route path="/ranking" element={<Ranking />} />
            <Route path="/create" element={<Placeholder title="問題をつくる" phase="フェーズ7" />} />
            <Route path="/mypage" element={<MyPage />} />
          </Route>
          <Route element={<FullScreenShell />}>
            <Route path="/solo/:category" element={<QuestionPicker />} />
            <Route path="/quiz" element={<QuizSession />} />
            <Route path="/battle/:code" element={<BattleRoom />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
