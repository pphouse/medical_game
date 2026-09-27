import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  api: {
    adminStats: vi.fn(),
    adminQuestion: vi.fn(),
  },
}));

import { api } from "../api";
import AdminQuestionEdit from "../routes/Admin/QuestionEdit";

// サーバは科目立てを試験種別ごとに返す（CBT と国試で切り方が違うため）。
const STATS = {
  canonical_categories: {
    CBT: ["循環器", "小児（成長と発達）", "救急・中毒・麻酔"],
    KOKUSHI: ["循環器", "小児科", "放射線科"],
  },
};

function renderNew() {
  return render(
    <MemoryRouter initialEntries={["/admin/questions/new"]}>
      <Routes>
        <Route path="/admin/questions/new" element={<AdminQuestionEdit />} />
      </Routes>
    </MemoryRouter>,
  );
}

function categoryOptions() {
  const select = screen.getByLabelText("分野");
  return within(select)
    .getAllByRole("option")
    .map((o) => o.value)
    .filter(Boolean);
}

describe("管理画面の問題編集: 分野の選択肢", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.adminStats.mockResolvedValue(STATS);
  });

  it("選んでいる試験種別の科目だけを出す", async () => {
    renderNew();
    await waitFor(() => expect(categoryOptions()).toContain("小児（成長と発達）"));
    expect(categoryOptions()).toEqual(["循環器", "小児（成長と発達）", "救急・中毒・麻酔"]);
  });

  it("試験種別を切り替えると科目も切り替わる", async () => {
    renderNew();
    await waitFor(() => expect(categoryOptions()).toContain("救急・中毒・麻酔"));
    fireEvent.change(screen.getByLabelText("試験種別"), { target: { value: "KOKUSHI" } });
    expect(categoryOptions()).toEqual(["循環器", "小児科", "放射線科"]);
  });
});
