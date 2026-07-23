import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import BottomNav from "./components/BottomNav";
import Home from "./components/Home";
import MyPage from "./components/MyPage";
import QuestionPicker from "./components/QuestionPicker";
import ReviewDeck from "./components/ReviewDeck";
import { ProfileProvider } from "./context/ProfileContext";
import { useSession } from "./hooks/useSession";
import Auth from "./routes/Auth";
import Battle from "./components/Battle";
import QuizSession from "./routes/QuizSession";
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
            <Route path="/" element={<Home />} />
            <Route path="/review" element={<ReviewDeck />} />
            <Route path="/battle" element={<Battle />} />
            <Route path="/mypage" element={<MyPage />} />
          </Route>
          <Route element={<FullScreenShell />}>
            <Route path="/solo/:category" element={<QuestionPicker />} />
            <Route path="/quiz" element={<QuizSession />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
