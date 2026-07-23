import { supabase } from "./lib/supabase";

const BASE_URL = "/api";

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

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

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
      if (text) message = `${message}: ${text.slice(0, 300)}`;
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return null;
  return res.json();
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
  progress: () => get("/quiz/progress/"),
  summary: () => get("/quiz/summary/"),
  questions: async (category, params = {}) => {
    // The endpoint is paginated (spec §6); the picker needs the whole
    // category at once for its mastery chips, so request the max page.
    const query = new URLSearchParams({ category, page_size: 500, ...params });
    const data = await get(`/quiz/questions/?${query}`);
    return data.results ?? data;
  },
  reviewDeck: () => get("/quiz/review-deck/"),

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
  battleStart: (code) => post(`/battle/rooms/${code}/start/`),
  battleState: (code) => get(`/battle/rooms/${code}/state/`),
  battleResult: (code) => get(`/battle/rooms/${code}/result/`),
  battleBuzz: (roundId) => post(`/battle/rounds/${roundId}/buzz/`),
  battleAnswer: (roundId, selectedChoiceKey) =>
    post(`/battle/rounds/${roundId}/answer/`, { selected_choice_key: selectedChoiceKey }),

  // rankings (phase 3)
  ranking: ({ scope, metric, period }) => {
    const query = new URLSearchParams({ scope, metric, period });
    return get(`/ranking/?${query}`);
  },
  rankingExams: () => get("/ranking/exams/"),
  submitAnswer: (payload) => post("/quiz/answers/", payload),
  submitMastery: (answerHistoryId, masteryLevel) =>
    post(`/quiz/answers/${answerHistoryId}/mastery/`, { mastery_level: masteryLevel }),
};
