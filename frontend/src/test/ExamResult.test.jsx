import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Result from "../routes/Exams/Result";

vi.mock("../lib/supabase", () => ({ supabase: null, isSupabaseConfigured: false }));
vi.mock("../api", () => ({ api: { examResult: vi.fn() } }));

import { api } from "../api";

const REVIEW = [
  {
    order: 1,
    question_id: 11,
    category: "循環器",
    exam_type: "CBT",
    difficulty: 2,
    question_text: "正解した設問",
    choices: [
      { key: "A", text: "あ" },
      { key: "B", text: "い" },
    ],
    correct_choice_key: "A",
    explanation: "1問目の解説",
    my_choice: "A",
    answered: true,
    correct: true,
  },
  {
    order: 2,
    question_id: 12,
    category: "呼吸器",
    exam_type: "CBT",
    difficulty: 2,
    question_text: "間違えた設問",
    choices: [
      { key: "A", text: "あ" },
      { key: "B", text: "い" },
    ],
    correct_choice_key: "B",
    explanation: "2問目の解説",
    my_choice: "A",
    answered: true,
    correct: false,
  },
];

function renderResult() {
  return render(
    <MemoryRouter initialEntries={["/exams/1/result"]}>
      <Routes>
        <Route path="/exams/:examId/result" element={<Result />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("模試の結果画面", () => {
  beforeEach(() => vi.clearAllMocks());

  it("提出直後でも得点・正誤・解説を出す", async () => {
    api.examResult.mockResolvedValue({
      status: "submitted",
      title: "月次実力テスト（CBT）",
      kind: "monthly",
      exam_type: "CBT",
      score: 1,
      max_score: 2,
      review: REVIEW,
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();

    expect(await screen.findByText("月次実力テスト（CBT） 結果")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("/2")).toBeInTheDocument();
    // どこを間違えたかと解説
    expect(screen.getByText("間違えた設問")).toBeInTheDocument();
    expect(screen.getByText("2問目の解説")).toBeInTheDocument();
    expect(screen.getByText(/あなたの解答: A ／ 正解: B/)).toBeInTheDocument();
  });

  it("成績はランキングタブで見られると案内する", async () => {
    api.examResult.mockResolvedValue({
      status: "submitted",
      title: "月次実力テスト（CBT）",
      score: 1,
      max_score: 2,
      review: REVIEW,
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();

    expect(await screen.findByText("成績は集計中です")).toBeInTheDocument();
    expect(screen.getByText(/2026年10月1日.*「ランキング」タブ/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ランキングを見る" })).toHaveAttribute(
      "href",
      "/ranking?category=exams",
    );
  });

  it("集計前は順位や偏差値の枠を出さない", async () => {
    api.examResult.mockResolvedValue({
      status: "submitted",
      title: "月次実力テスト（CBT）",
      score: 1,
      max_score: 2,
      review: REVIEW,
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();

    await screen.findByText("見直し");
    expect(screen.queryByText("全国順位")).not.toBeInTheDocument();
    expect(screen.queryByText("偏差値")).not.toBeInTheDocument();
    expect(screen.queryByText("分野別スコア")).not.toBeInTheDocument();
  });

  it("模試の問題を問題演習で解き直す導線を出す", async () => {
    api.examResult.mockResolvedValue({
      status: "submitted",
      title: "月次実力テスト（CBT）",
      score: 1,
      max_score: 2,
      review: REVIEW,
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();

    expect(
      await screen.findByRole("button", { name: "この模試の問題を演習する ▶" }),
    ).toBeInTheDocument();
  });

  it("採点後は順位・偏差値・分野別スコアも出す", async () => {
    api.examResult.mockResolvedValue({
      status: "graded",
      title: "月次実力テスト（CBT）",
      score: 1,
      max_score: 2,
      rank: 3,
      out_of: 10,
      percentile: 70,
      university_rank: 1,
      deviation_score: 58.2,
      section_scores: { "D-5": 1.0 },
      section_deviation_scores: {},
      review: REVIEW,
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();

    expect(await screen.findByText("全国順位")).toBeInTheDocument();
    expect(screen.getByText("偏差値")).toBeInTheDocument();
    expect(screen.getByText("分野別スコア")).toBeInTheDocument();
    // 集計待ちの案内は出さない
    expect(screen.queryByText("成績は集計中です")).not.toBeInTheDocument();
  });
});
