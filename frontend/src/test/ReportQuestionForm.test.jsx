/**
 * 問題の下に置く「間違い・不具合を報告」フォーム。
 *
 * 送信したら閉じて元の問題の画面に戻ること、理由を選ばずには送れないこと、
 * 次の問題に進んだら前の入力を持ち越さないことを見る。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReportQuestionForm from "../components/ReportQuestionForm";

vi.mock("../api", () => ({ api: { reportQuestion: vi.fn() } }));

import { api } from "../api";

function open() {
  fireEvent.click(screen.getByRole("button", { name: "間違い・不具合を報告" }));
}

describe("間違い・不具合の報告", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.reportQuestion.mockResolvedValue({ reported: true, report_count: 1 });
  });

  it("文字を押すと、3つの選択肢と記述欄が出る", () => {
    render(<ReportQuestionForm questionId={7} />);
    open();

    for (const label of ["問題文が間違っている", "解答が間違っている", "その他"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByPlaceholderText(/気づいたことがあれば/)).toBeInTheDocument();
  });

  it("理由を選ぶまで送信できない", () => {
    render(<ReportQuestionForm questionId={7} />);
    open();

    expect(screen.getByRole("button", { name: "フォームを送信する" })).toBeDisabled();

    fireEvent.click(screen.getByLabelText("解答が間違っている"));

    expect(screen.getByRole("button", { name: "フォームを送信する" })).toBeEnabled();
  });

  it("複数選べて、記述欄と一緒に送られる", async () => {
    render(<ReportQuestionForm questionId={7} />);
    open();

    fireEvent.click(screen.getByLabelText("問題文が間違っている"));
    fireEvent.click(screen.getByLabelText("解答が間違っている"));
    fireEvent.change(screen.getByPlaceholderText(/気づいたことがあれば/), {
      target: { value: "選択肢Bも正解になりそうです" },
    });
    fireEvent.click(screen.getByRole("button", { name: "フォームを送信する" }));

    await waitFor(() =>
      expect(api.reportQuestion).toHaveBeenCalledWith(7, {
        reasons: ["wrong_question", "wrong_answer"],
        detail: "選択肢Bも正解になりそうです",
      }),
    );
  });

  it("送信すると閉じて、元の問題の画面に戻る", async () => {
    render(<ReportQuestionForm questionId={7} />);
    open();
    fireEvent.click(screen.getByLabelText("その他"));
    fireEvent.click(screen.getByRole("button", { name: "フォームを送信する" }));

    expect(await screen.findByText(/報告しました/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "フォームを送信する" })).not.toBeInTheDocument();
  });

  it("送信に失敗したら、入力を残したまま理由を出す", async () => {
    api.reportQuestion.mockRejectedValue(new Error("この問題はすでに通報済みです。"));
    render(<ReportQuestionForm questionId={7} />);
    open();
    fireEvent.click(screen.getByLabelText("その他"));
    fireEvent.click(screen.getByRole("button", { name: "フォームを送信する" }));

    expect(await screen.findByText("この問題はすでに通報済みです。")).toBeInTheDocument();
    expect(screen.getByLabelText("その他")).toBeChecked();
  });

  it("次の問題に進むと、前の問題の入力は残らない", () => {
    const { rerender } = render(<ReportQuestionForm questionId={7} />);
    open();
    fireEvent.click(screen.getByLabelText("その他"));

    rerender(<ReportQuestionForm questionId={8} />);

    expect(screen.getByRole("button", { name: "間違い・不具合を報告" })).toBeInTheDocument();
  });
});
