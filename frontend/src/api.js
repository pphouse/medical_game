const BASE_URL = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  demoLogin: () => request("/auth/demo-login/", { method: "POST" }),
  me: () => request("/auth/me/"),
  categories: () => request("/quiz/categories/"),
  progress: () => request("/quiz/progress/"),
  summary: () => request("/quiz/summary/"),
  questions: (category) =>
    request(`/quiz/questions/?category=${encodeURIComponent(category)}`),
  reviewDeck: () => request("/quiz/review-deck/"),
  submitAnswer: (payload) =>
    request("/quiz/answers/", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitMastery: (answerHistoryId, masteryLevel) =>
    request(`/quiz/answers/${answerHistoryId}/mastery/`, {
      method: "POST",
      body: JSON.stringify({ mastery_level: masteryLevel }),
    }),
};
