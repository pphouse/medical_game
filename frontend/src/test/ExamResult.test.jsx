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

  it("選択肢を色分けし、正解と自分の解答を示す", async () => {
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

    // 2問目: 正解はB、自分はAを選んで外した
    const rows = document.querySelectorAll(".choice-note-row");
    const correct = [...rows].filter((r) => r.classList.contains("correct"));
    const incorrect = [...rows].filter((r) => r.classList.contains("incorrect"));
    // 1問目の正解A（＝自分の解答）と2問目の正解Bが緑
    expect(correct).toHaveLength(2);
    // 赤は「自分が選んで外した」2問目のAだけ（1問目は正解なので赤にしない）
    expect(incorrect).toHaveLength(1);
    // 正解と自分の解答が一致した1問目のAは緑のまま（赤にはならない）
    expect(correct[0].classList.contains("incorrect")).toBe(false);

    expect(screen.getAllByText("正解")).toHaveLength(2);
    expect(screen.getAllByText("あなたの解答")).toHaveLength(2);
  });

  it("選択肢ごとの解説は解説文のあとにまとめる", async () => {
    const withNotes = {
      ...REVIEW[1],
      choice_explanations: { A: "Aが誤りの理由", B: "Bが正解の理由" },
    };
    api.examResult.mockResolvedValue({
      status: "submitted",
      title: "月次実力テスト（CBT）",
      score: 0,
      max_score: 1,
      review: [withNotes],
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();
    await screen.findByText("見直し");

    expect(screen.getByText("選択肢ごとの解説")).toBeInTheDocument();
    expect(screen.getByText("Aが誤りの理由")).toBeInTheDocument();
    // 解説本文より後ろに置く（本文と行き来せずに読めるように）
    const card = document.querySelector(".exam-review-card");
    const text = card.textContent;
    expect(text.indexOf("2問目の解説")).toBeLessThan(text.indexOf("選択肢ごとの解説"));
  });

  it("選択肢ごとの解説が無い問題では見出しを出さない", async () => {
    api.examResult.mockResolvedValue({
      status: "submitted",
      title: "月次実力テスト（CBT）",
      score: 1,
      max_score: 1,
      review: [{ ...REVIEW[0], choice_explanations: {} }],
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();
    await screen.findByText("見直し");

    expect(screen.queryByText("選択肢ごとの解説")).not.toBeInTheDocument();
    // 選択肢の色分け一覧は残る
    expect(document.querySelectorAll(".choice-note-row")).toHaveLength(2);
  });

  it("解説の無い選択肢も一覧に並べる", async () => {
    api.examResult.mockResolvedValue({
      status: "submitted",
      title: "月次実力テスト（CBT）",
      score: 1,
      max_score: 2,
      review: [{ ...REVIEW[0], choice_explanations: {} }],
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();
    await screen.findByText("見直し");

    expect(document.querySelectorAll(".choice-note-row")).toHaveLength(2);
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
    // 解禁前は灰色で押せないボタン（リンクにはしない）。
    const button = screen.getByRole("button", { name: /成績を見る/ });
    expect(button).toBeDisabled();
    expect(button.textContent).toContain("2026年10月1日から");
    expect(screen.queryByRole("link", { name: "成績を見る" })).not.toBeInTheDocument();
  });

  it("成績が見られるようになったら押せるリンクにする", async () => {
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

    expect(await screen.findByText("成績を確認できます")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "成績を見る" })).toHaveAttribute(
      "href",
      "/ranking?category=exams",
    );
    expect(screen.queryByRole("button", { name: /成績を見る/ })).not.toBeInTheDocument();
  });

  it("左上の戻るで一つ前の画面に戻れる", async () => {
    api.examResult.mockResolvedValue({
      status: "submitted",
      title: "月次実力テスト（CBT）",
      score: 1,
      max_score: 2,
      review: REVIEW,
      ranking_available_at: "2026-10-01T00:00:00+09:00",
    });

    renderResult();

    expect(await screen.findByRole("button", { name: "← 戻る" })).toBeInTheDocument();
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
