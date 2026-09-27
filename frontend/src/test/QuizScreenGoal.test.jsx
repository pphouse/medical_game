import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ api: { submitAnswer: vi.fn(), submitMastery: vi.fn() } }));
vi.mock("../reminders", () => ({ syncReminders: vi.fn() }));

import { api } from "../api";
import QuizScreen from "../components/QuizScreen";
import { syncReminders } from "../reminders";

const QUESTIONS = [1, 2].map((id) => ({
  id,
  exam_type: "CBT",
  difficulty: 2,
  category: "循環器",
  correct_rate: null,
  question_text: `設問${id}`,
  choices: ["A", "B", "C", "D", "E"].map((key) => ({ key, text: `選択肢${key}` })),
}));

function answerResponse(dailyProgress) {
  return {
    answer_history_id: 1,
    correct: true,
    correct_choice_key: "A",
    explanation: "解説",
    choice_explanations: {},
    correct_rate: null,
    mastery_level: "circle",
    next_review_at: null,
    daily_progress: dailyProgress,
  };
}

function answer() {
  fireEvent.click(screen.getByRole("button", { name: /選択肢A/ }));
  fireEvent.click(screen.getByRole("button", { name: "解答する" }));
}

describe("解答中の今日の目標", () => {
  beforeEach(() => vi.clearAllMocks());

  it("解くたびに今日の数を出し、届いた瞬間にお祝いする", async () => {
    api.submitAnswer.mockResolvedValue(
      answerResponse({
        date: "2026-09-25",
        goal: 3,
        count: 3,
        remaining: 0,
        achieved: true,
        just_achieved: true,
        streak: 5,
      }),
    );
    render(<QuizScreen title="循環器" questions={QUESTIONS} onBack={vi.fn()} />);
    answer();

    expect(await screen.findByRole("dialog", { name: "今日の目標を達成！" })).toHaveTextContent(
      "3問クリア。5日連続です。",
    );
    expect(screen.getByLabelText("今日の目標")).toHaveTextContent("今日 3/3");
    expect(syncReminders).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "続ける" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("届く前はお祝いを出さない", async () => {
    api.submitAnswer.mockResolvedValue(
      answerResponse({
        date: "2026-09-25",
        goal: 3,
        count: 1,
        remaining: 2,
        achieved: false,
        just_achieved: false,
      }),
    );
    render(<QuizScreen title="循環器" questions={QUESTIONS} onBack={vi.fn()} />);
    answer();

    await waitFor(() => expect(screen.getByLabelText("今日の目標")).toHaveTextContent("今日 1/3"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(syncReminders).not.toHaveBeenCalled();
  });

  it("目標が無い人・進み具合が取れないときは何も出さない", async () => {
    api.submitAnswer.mockResolvedValue(answerResponse(null));
    render(<QuizScreen title="循環器" questions={QUESTIONS} onBack={vi.fn()} />);
    answer();

    await screen.findByText("○ 正解！");
    expect(screen.queryByLabelText("今日の目標")).not.toBeInTheDocument();
  });
});
