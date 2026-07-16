import { useEffect, useState } from "react";
import { api } from "./api";
import Home from "./components/Home";
import Battle from "./components/Battle";
import MyPage from "./components/MyPage";
import QuestionPicker from "./components/QuestionPicker";
import QuizScreen from "./components/QuizScreen";
import ReviewDeck from "./components/ReviewDeck";
import BottomNav from "./components/BottomNav";
import "./App.css";

// tab: "home" | "review" | "battle" | "mypage"
export default function App() {
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("home");
  const [pickerCategory, setPickerCategory] = useState(null);
  const [quizSession, setQuizSession] = useState(null); // { title, questions } | null

  useEffect(() => {
    api
      .demoLogin()
      .then(setUser)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="screen">
        <h2>接続エラー</h2>
        <p className="error">{error}</p>
        <p>Djangoサーバー（http://127.0.0.1:8000）が起動しているか確認してください。</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="screen">
        <p>読み込み中...</p>
      </div>
    );
  }

  if (quizSession) {
    return (
      <div className="app-shell">
        <QuizScreen
          title={quizSession.title}
          questions={quizSession.questions}
          onBack={() => setQuizSession(null)}
        />
      </div>
    );
  }

  if (pickerCategory) {
    return (
      <div className="app-shell">
        <QuestionPicker
          category={pickerCategory}
          onBack={() => setPickerCategory(null)}
          onStart={(session) => {
            setPickerCategory(null);
            setQuizSession(session);
          }}
        />
      </div>
    );
  }

  return (
    <div className="app-shell with-bottom-nav">
      {tab === "home" && <Home user={user} onSelectCategory={setPickerCategory} />}
      {tab === "review" && (
        <ReviewDeck onBack={() => setQuizSession(null)} onStartSession={setQuizSession} />
      )}
      {tab === "battle" && <Battle />}
      {tab === "mypage" && <MyPage user={user} />}
      <BottomNav active={tab} onChange={setTab} />
    </div>
  );
}
