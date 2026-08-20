import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  api: {
    adminStats: vi.fn(),
    adminQuestions: vi.fn(),
    adminBulkStatus: vi.fn(),
  },
}));

vi.mock("../context/ProfileContext", () => ({
  useProfile: vi.fn(),
}));

import { api } from "../api";
import { useProfile } from "../context/ProfileContext";
import AdminLayout from "../routes/Admin/Layout";
import AdminQuestions from "../routes/Admin/Questions";

function renderAdmin(initialEntries = ["/admin"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/admin" element={<AdminLayout />}>
          <Route path="questions" element={<AdminQuestions />} />
        </Route>
        <Route path="/" element={<p>ホーム画面</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("管理画面のガード", () => {
  beforeEach(() => vi.clearAllMocks());

  it("学生は入れずホームへ飛ばされる", async () => {
    useProfile.mockReturnValue({ profile: { id: "u1", role: "student" } });
    renderAdmin();
    expect(await screen.findByText("ホーム画面")).toBeInTheDocument();
  });

  it("モデレーターはユーザー管理タブを見られない", () => {
    useProfile.mockReturnValue({ profile: { id: "u1", role: "moderator" } });
    renderAdmin();
    expect(screen.getByText("問題")).toBeInTheDocument();
    expect(screen.queryByText("ユーザー")).not.toBeInTheDocument();
  });

  it("管理者はユーザー管理タブを見られる", () => {
    useProfile.mockReturnValue({ profile: { id: "u1", role: "admin" } });
    renderAdmin();
    expect(screen.getByText("ユーザー")).toBeInTheDocument();
  });
});

describe("管理画面の問題一覧", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProfile.mockReturnValue({ profile: { id: "u1", role: "admin" } });
  });

  const page = {
    count: 2,
    next: null,
    previous: null,
    results: [
      {
        id: 1,
        question_text: "審査待ちの設問",
        status: "pending",
        exam_type: "CBT",
        category: "循環器系",
        answer_count: 0,
        report_count: 0,
      },
      {
        id: 2,
        question_text: "通報のある設問",
        status: "published",
        exam_type: "KOKUSHI",
        category: "呼吸器系",
        answer_count: 12,
        report_count: 3,
      },
    ],
  };

  it("状態・試験・通報件数を出す", async () => {
    api.adminQuestions.mockResolvedValue(page);
    renderAdmin(["/admin/questions"]);

    expect(await screen.findByText("審査待ちの設問")).toBeInTheDocument();
    expect(screen.getByText("通報3件")).toBeInTheDocument();
    expect(screen.getByText("解答12件")).toBeInTheDocument();
  });

  it("URLの絞り込みをそのままAPIに渡す", async () => {
    api.adminQuestions.mockResolvedValue(page);
    renderAdmin(["/admin/questions?status=pending&exam_type=CBT"]);

    await waitFor(() =>
      expect(api.adminQuestions).toHaveBeenCalledWith(
        expect.objectContaining({ status: "pending", exam_type: "CBT" }),
      ),
    );
  });

  it("選択した問題だけを一括で公開する", async () => {
    api.adminQuestions.mockResolvedValue(page);
    api.adminBulkStatus.mockResolvedValue({ updated: 1, status: "published" });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderAdmin(["/admin/questions"]);
    await screen.findByText("審査待ちの設問");

    const checkboxes = screen.getAllByRole("checkbox");
    // 先頭は「このページを全選択」、以降が各行
    fireEvent.click(checkboxes[1]);
    fireEvent.click(screen.getByRole("button", { name: "公開" }));

    await waitFor(() =>
      expect(api.adminBulkStatus).toHaveBeenCalledWith({ ids: [1], status: "published" }),
    );
  });

  it("一致する全件の一括操作には件数を添えて誤爆を防ぐ", async () => {
    api.adminQuestions.mockResolvedValue(page);
    api.adminBulkStatus.mockResolvedValue({ updated: 2, status: "pending" });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderAdmin(["/admin/questions?status=published"]);
    await screen.findByText("審査待ちの設問");

    fireEvent.click(screen.getByRole("button", { name: "一致する2問すべてを非公開に" }));

    await waitFor(() =>
      expect(api.adminBulkStatus).toHaveBeenCalledWith({
        filters: expect.objectContaining({ status: "published" }),
        expected_count: 2,
        status: "pending",
      }),
    );
    // page は絞り込み条件ではないので送らない
    expect(api.adminBulkStatus.mock.calls[0][0].filters.page).toBeUndefined();
  });
});
