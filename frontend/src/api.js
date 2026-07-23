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
  questions: (category, params = {}) => {
    const query = new URLSearchParams({ category, ...params });
    return get(`/quiz/questions/?${query}`);
  },
  reviewDeck: () => get("/quiz/review-deck/"),
  submitAnswer: (payload) => post("/quiz/answers/", payload),
  submitMastery: (answerHistoryId, masteryLevel) =>
    post(`/quiz/answers/${answerHistoryId}/mastery/`, { mastery_level: masteryLevel }),
};
