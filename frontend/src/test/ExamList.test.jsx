import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ExamList from "../components/ExamList";

vi.mock("../lib/supabase", () => ({ supabase: null, isSupabaseConfigured: false }));
vi.mock("../api", () => ({ api: { exams: vi.fn(), examStart: vi.fn() } }));

import { api } from "../api";

function exam(id, status, overrides = {}) {
  return {
    id,
    title: `模試${id}`,
    kind: "monthly",
    exam_type: "CBT",
    status,
    question_count: 15,
    duration_minutes: 20,
    target_grade_min: null,
    target_grade_max: 4,
    my_result: null,
    ...overrides,
  };
}

function renderList() {
  return render(
    <MemoryRouter>
      <ExamList />
    </MemoryRouter>,
  );
}

/** 見出しの並び順（点線で区切られるセクションの順序）。 */
function sectionOrder() {
  return [...document.querySelectorAll(".exam-section-heading")].map((h) => h.textContent);
}

describe("模試一覧", () => {
  beforeEach(() => vi.clearAllMocks());

  it("受験できる模試を一番上に、開催予定・開催済みをその下に並べる", async () => {
    api.exams.mockResolvedValue([
      exam(1, "scheduled"),
      exam(2, "graded"),
      exam(3, "open"),
    ]);

    renderList();

    await screen.findByText("受験できる模試");
    expect(sectionOrder()).toEqual([
      "受験できる模試",
      "開催予定",
      "開催済み",
      "模試の種類",
    ]);
  });

  it("受験できない区分は点線で区切る", async () => {
    api.exams.mockResolvedValue([exam(1, "open")]);

    renderList();
    await screen.findByText("受験できる模試");

    const sections = [...document.querySelectorAll(".exam-section")];
    // 先頭（受験できる模試）には区切りを付けず、以降に付ける
    expect(sections[0].classList.contains("exam-section-divided")).toBe(false);
    expect(sections.slice(1).every((s) => s.classList.contains("exam-section-divided"))).toBe(
      true,
    );
  });

  it("提出済みの模試は受験できる側ではなく開催済みに入れる", async () => {
    api.exams.mockResolvedValue([
      exam(1, "open", { my_result: { started_at: "x", submitted_at: "y" } }),
    ]);

    renderList();
    await screen.findByText("受験できる模試");

    const available = document.querySelectorAll(".exam-section")[0];
    const past = document.querySelectorAll(".exam-section")[2];
    expect(available.textContent).toContain("いま受験できる模試はありません");
    expect(past.textContent).toContain("模試1");
  });

  it("空の区分にもその旨を出す", async () => {
    api.exams.mockResolvedValue([]);

    renderList();

    expect(await screen.findByText("いま受験できる模試はありません。")).toBeInTheDocument();
    expect(screen.getByText("開催予定の模試はありません。")).toBeInTheDocument();
  });

  it("模試の種類の概要は常に出す", async () => {
    api.exams.mockResolvedValue([exam(1, "open")]);

    renderList();

    expect(await screen.findByText("模試の種類")).toBeInTheDocument();
    // 概要と「受けられない理由」の両方に出るので複数一致でよい。
    expect(screen.getAllByText(/受験可能期間は7月1日から3月31日まで/).length).toBeGreaterThan(0);
  });
});
