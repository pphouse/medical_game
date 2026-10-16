/**
 * 左上の戻るは、履歴を1つ戻るのではなく決まった親の画面へ1段階ずつ出る。
 *
 * 履歴だと、戻った先からまたその画面へ入れる作り（模試の採点結果 ⇄ 復習の
 * 演習）で2画面を行き来するだけになり、一覧まで抜け出せなかった。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import QuizSession from "../routes/QuizSession";

vi.mock("../lib/supabase", () => ({ supabase: null, isSupabaseConfigured: false }));
vi.mock("../api", () => ({ api: { submitAnswer: vi.fn(), submitMastery: vi.fn() } }));

const QUESTION = {
  id: 1,
  category: "循環器",
  exam_type: "CBT",
  difficulty: 2,
  question_text: "設問",
  choices: [
    { key: "A", text: "あ" },
    { key: "B", text: "い" },
  ],
};

function renderSession(state) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/quiz", state }]}>
      <Routes>
        <Route path="/quiz" element={<QuizSession />} />
        <Route path="/exams/1/result" element={<div>採点結果</div>} />
        <Route path="/solo/循環器" element={<div>問題一覧</div>} />
        <Route path="/" element={<div>ホーム</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("出題画面の戻る", () => {
  it("模試の復習からは採点結果へ出る", () => {
    renderSession({
      questions: [QUESTION],
      title: "月次実力テスト",
      backTo: "/exams/1/result",
      backLabel: "採点結果へ",
    });

    fireEvent.click(screen.getByRole("button", { name: "← 採点結果へ" }));

    expect(screen.getByText("採点結果")).toBeInTheDocument();
  });

  it("分野別演習からは問題一覧へ出る", () => {
    renderSession({
      questions: [QUESTION],
      title: "循環器",
      backTo: "/solo/循環器",
      backLabel: "問題一覧へ",
    });

    fireEvent.click(screen.getByRole("button", { name: "← 問題一覧へ" }));

    expect(screen.getByText("問題一覧")).toBeInTheDocument();
  });

  it("戻り先の指定が無ければホームへ出る（履歴は見ない）", () => {
    renderSession({ questions: [QUESTION], title: "演習" });

    fireEvent.click(screen.getByRole("button", { name: "← ホームへ" }));

    expect(screen.getByText("ホーム")).toBeInTheDocument();
  });
});
