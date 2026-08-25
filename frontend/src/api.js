import { supabase } from "./lib/supabase";

// Same-origin "/api" by default (dev proxy / same-domain deploy). Set
// VITE_API_BASE_URL to the backend origin when the Django API is hosted on a
// different domain than the frontend (e.g. a separate Vercel project).
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function getAccessToken() {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers ?? {}) };
  const token = await getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const url = `${BASE_URL}${path}`;
  let res;
  try {
    res = await fetch(url, { ...options, headers });
  } catch {
    // fetch 自体が失敗するのは、宛先に届いていないか CORS で弾かれた場合。
    // ステータスが無いので、どこへ繋ごうとしたかを出さないと切り分けられない。
    throw new ApiError(
      0,
      `APIに接続できませんでした（${url}）。接続先の設定（VITE_API_BASE_URL）と` +
        "バックエンドのCORS設定を確認してください。",
    );
  }

  if (res.status === 401) {
    // Token expired/revoked: clear the session and send the user to /auth
    // (spec §5-9: treat 401 as session expiry, not a generic error).
    if (supabase) await supabase.auth.signOut();
    if (!window.location.pathname.startsWith("/auth")) {
      window.location.assign("/auth?reason=expired");
    }
    throw new ApiError(401, "ログインの有効期限が切れました。もう一度ログインしてください。");
  }

  if (!res.ok) {
    const text = await res.text();
    let message = `APIエラー (${res.status})`;
    try {
      const body = JSON.parse(text);
      if (typeof body.detail === "string") message = body.detail;
      else message = `${message}: ${text}`;
    } catch {
      // JSON で返らないのはバックエンドの手前で止まっている合図（Django の
      // エラーページや、SPA のリライトに吸われた index.html）。宛先を添える。
      message = `${message} ${url}`;
      if (text) message = `${message}: ${text.slice(0, 200)}`;
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return null;

  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    // 200 なのに JSON でない典型は、VITE_API_BASE_URL が未設定でフロント自身の
    // オリジンを叩き、SPA のリライトで index.html が返っている場合。
    throw new ApiError(
      res.status,
      `APIがJSONを返しませんでした（${url}）。接続先の設定（VITE_API_BASE_URL）が` +
        "バックエンドのURLになっているか確認してください。",
    );
  }
}

const get = (path) => request(path);
const post = (path, payload) =>
  request(path, { method: "POST", body: payload === undefined ? undefined : JSON.stringify(payload) });
const patch = (path, payload) =>
  request(path, { method: "PATCH", body: JSON.stringify(payload) });

export const api = {
  // auth / profile
  bootstrap: (payload = {}) => post("/auth/bootstrap/", payload),
  me: () => get("/auth/me/"),
  updateMe: (payload) => patch("/auth/me/", payload),
  universities: () => get("/auth/universities/"),

  // solo quiz
  categories: () => get("/quiz/categories/"),
  // examType: "CBT" | "KOKUSHI" | undefined（未指定は全部）
  progress: (examType) =>
    get(`/quiz/progress/${examType ? `?exam_type=${encodeURIComponent(examType)}` : ""}`),
  summary: () => get("/quiz/summary/"),
  questions: async (category, params = {}) => {
    // The endpoint is paginated (spec §6); the picker needs the whole
    // category at once for its mastery chips, so request the max page.
    const query = new URLSearchParams({ category, page_size: 500, ...params });
    const data = await get(`/quiz/questions/?${query}`);
    return data.results ?? data;
  },
  reviewDeck: () => get("/quiz/review-deck/"),
  reviewSummary: () => get("/quiz/review-deck/summary/"),
  // 科目・評価・演習回数で絞った演習セット。空配列は「絞り込まない」。
  reviewFilter: ({ categories = [], mastery = [], attempts = [], examType } = {}) => {
    const query = new URLSearchParams();
    if (categories.length) query.set("categories", categories.join(","));
    if (mastery.length) query.set("mastery", mastery.join(","));
    if (attempts.length) query.set("attempts", attempts.join(","));
    if (examType) query.set("exam_type", examType);
    return get(`/quiz/review-filter/?${query}`);
  },

  // user question creation (phase 7)
  createQuestion: (payload) => post("/quiz/questions/", payload),
  myQuestions: () => get("/quiz/my-questions/"),
  updateQuestion: (id, payload) => patch(`/quiz/questions/${id}/`, payload),
  deleteQuestion: (id) => request(`/quiz/questions/${id}/`, { method: "DELETE" }),
  submitQuestionForReview: (id) => post(`/quiz/questions/${id}/submit/`),
  reportQuestion: (id, payload) => post(`/quiz/questions/${id}/report/`, payload),

  // admin (moderator/admin only)
  adminStats: () => get("/admin/stats/"),
  adminQuestions: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "" && v != null)),
    );
    return get(`/admin/questions/?${query}`);
  },
  adminQuestion: (id) => get(`/admin/questions/${id}/`),
  adminCreateQuestion: (payload) => post("/admin/questions/", payload),
  adminUpdateQuestion: (id, payload) => patch(`/admin/questions/${id}/`, payload),
  adminDeleteQuestion: (id) => request(`/admin/questions/${id}/`, { method: "DELETE" }),
  adminBulkStatus: (payload) => post("/admin/questions/bulk-status/", payload),
  adminReports: () => get("/admin/reports/"),
  adminUsers: () => get("/admin/users/"),
  adminSetUserRole: (id, role) => patch("/admin/users/", { id, role }),

  // student verification (phase 7)
  verificationStatus: () => get("/auth/student-verification/"),
  applyVerification: (universityId) =>
    post("/auth/student-verification/", { university_id: universityId }),
  completeVerification: (id) => patch(`/auth/student-verification/${id}/complete/`, {}),

  // mock exams (phase 5)
  exams: () => get("/exams/"),
  examStart: (id) => post(`/exams/${id}/start/`),
  examQuestions: (id) => get(`/exams/${id}/questions/`),
  examAnswer: (id, payload) => post(`/exams/${id}/answers/`, payload),
  examSubmit: (id) => post(`/exams/${id}/submit/`),
  examResult: (id) => get(`/exams/${id}/result/`),

  // battle (phase 4)
  battleCreate: (payload) => post("/battle/rooms/", payload),
  battleJoin: (code) => post(`/battle/rooms/${code}/join/`),
  // 待機中はルームから抜けるだけ、対戦中はスコアを凍結してAIと入れ替わる。
  battleLeave: (code) => post(`/battle/rooms/${code}/leave/`),
  battleStart: (code) => post(`/battle/rooms/${code}/start/`),
  battleState: (code) => get(`/battle/rooms/${code}/state/`),
  battleResult: (code) => get(`/battle/rooms/${code}/result/`),
  battleBuzz: (roundId) => post(`/battle/rounds/${roundId}/buzz/`),
  battleAnswer: (roundId, selectedChoiceKey) =>
    post(`/battle/rounds/${roundId}/answer/`, { selected_choice_key: selectedChoiceKey }),

  // 対戦クイックマッチ（同ランク優先マッチング・1分でAI対戦フォールバック）
  battleQuickMatch: (questionCount) =>
    post("/battle/quickmatch/", { question_count: questionCount }),
  battleQuickMatchPoll: (ticketId) => get(`/battle/quickmatch/${ticketId}/`),

  // rankings (phase 3)
  ranking: ({ scope, metric, period }) => {
    const query = new URLSearchParams({ scope, metric, period });
    return get(`/ranking/?${query}`);
  },
  rankingExams: () => get("/ranking/exams/"),
  // 順位クリック時の詳細（散布図・直近30日の演習数・昨日の演習状況）
  rankDetail: (scope, metric) =>
    get(`/ranking/detail/?${new URLSearchParams({ scope, metric })}`),
  // 対戦＋模試（週次/月次）合算ポイントランキング（SS〜Dランク）
  pointsRanking: (scope) => get(`/ranking/points/?${new URLSearchParams({ scope })}`),
  submitAnswer: (payload) => post("/quiz/answers/", payload),
  submitMastery: (answerHistoryId, masteryLevel) =>
    post(`/quiz/answers/${answerHistoryId}/mastery/`, { mastery_level: masteryLevel }),
};
