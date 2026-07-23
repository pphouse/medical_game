import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Match from "../routes/Battle/Match";
import Room from "../routes/Battle/Room";

vi.mock("../lib/supabase", () => ({ supabase: null, isSupabaseConfigured: false }));
vi.mock("../api", () => ({
  api: {
    battleState: vi.fn(),
    battleStart: vi.fn(),
    battleResult: vi.fn(),
    battleBuzz: vi.fn(),
    battleAnswer: vi.fn(),
  },
}));

import { api } from "../api";

function renderRoom() {
  return render(
    <MemoryRouter initialEntries={["/battle/123456"]}>
      <Routes>
        <Route path="/battle/:code" element={<Room />} />
      </Routes>
    </MemoryRouter>
  );
}

const WAITING = {
  room: { room_code: "123456", status: "waiting", question_count: 5 },
  participants: [
    { display_name: "ホスト", is_host: true, is_me: true, connected: true },
  ],
};

function inProgress(roundOverrides = {}) {
  return {
    room: { room_code: "123456", status: "in_progress", question_count: 5 },
    participants: [
      { display_name: "ホスト", is_host: true, is_me: true, connected: true, score: 100 },
      { display_name: "相手", is_host: false, is_me: false, connected: true, score: 80 },
    ],
    last_result: null,
    round: {
      id: 7,
      number: 2,
      total: 5,
      closes_at: new Date(Date.now() + 30_000).toISOString(),
      can_buzz: true,
      i_am_answering: false,
      answering_rank: null,
      buzzes: [],
      question: {
        question_text: "心不全の急性期治療で最も適切なのはどれか。",
        case_stem: null,
        choices: [
          { key: "A", text: "利尿薬" },
          { key: "B", text: "抗菌薬" },
        ],
      },
      ...roundOverrides,
    },
  };
}

describe("対戦ルームの状態遷移 (Room)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("waiting: ルームコードと参加者を表示し、1人では開始できない", async () => {
    api.battleState.mockResolvedValue(WAITING);

    renderRoom();

    expect(await screen.findByText("123456")).toBeInTheDocument();
    expect(screen.getByText(/ホスト/)).toBeInTheDocument();
    const startButton = screen.getByRole("button", { name: "2人以上で開始できます" });
    expect(startButton).toBeDisabled();
  });

  it("ポーリングで waiting → in_progress に遷移すると出題画面になる", async () => {
    api.battleState
      .mockResolvedValueOnce(WAITING)
      .mockResolvedValue(inProgress());

    renderRoom();

    expect(await screen.findByText("対戦ルーム")).toBeInTheDocument();

    // 1.5秒間隔のポーリングが次の state を取り込む
    expect(
      await screen.findByText(
        "心不全の急性期治療で最も適切なのはどれか。",
        undefined,
        { timeout: 4000 }
      )
    ).toBeInTheDocument();
    expect(screen.getByText("第2問 / 5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "早押し！" })).toBeInTheDocument();
  });

  it("finished: 結果画面（順位と点数）を表示する", async () => {
    api.battleState.mockResolvedValue({
      room: { room_code: "123456", status: "finished", question_count: 5 },
      participants: [],
    });
    api.battleResult.mockResolvedValue({
      standings: [
        { rank: 1, display_name: "ホスト", is_me: true, score: 320, correct_count: 4 },
        { rank: 2, display_name: "相手", is_me: false, score: 180, correct_count: 2 },
      ],
    });

    renderRoom();

    expect(await screen.findByText("対戦結果")).toBeInTheDocument();
    expect(screen.getByText("320点")).toBeInTheDocument();
    expect(screen.getByText("正解 4問")).toBeInTheDocument();
  });
});

describe("対戦ラウンド内の状態 (Match)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("早押し可能: 早押しボタンが出て、選択肢は押せない", () => {
    const state = inProgress();
    render(<Match state={state} refresh={vi.fn()} />);

    expect(screen.getByRole("button", { name: "早押し！" })).toBeEnabled();
    expect(screen.getByRole("button", { name: /利尿薬/ })).toBeDisabled();
  });

  it("回答権あり: 選択肢が有効になり、回答すると API が呼ばれる", async () => {
    api.battleAnswer.mockResolvedValue({});
    const refresh = vi.fn().mockResolvedValue();
    const state = inProgress({
      can_buzz: false,
      i_am_answering: true,
      buzzes: [{ rank: 1, display_name: "ホスト", is_me: true, is_correct: null }],
    });
    render(<Match state={state} refresh={refresh} />);

    expect(
      screen.getByText("回答権があります。選択肢を選んでください！")
    ).toBeInTheDocument();
    const choice = screen.getByRole("button", { name: /利尿薬/ });
    expect(choice).toBeEnabled();

    fireEvent.click(choice);
    await waitFor(() => expect(api.battleAnswer).toHaveBeenCalledWith(7, "A"));
    expect(refresh).toHaveBeenCalled();
  });

  it("他者の回答待ち: 待機メッセージと早押し順チップを表示する", () => {
    const state = inProgress({
      can_buzz: false,
      i_am_answering: false,
      answering_rank: 1,
      buzzes: [
        { rank: 1, display_name: "相手", is_me: false, is_correct: null },
        { rank: 2, display_name: "ホスト", is_me: true, is_correct: null },
      ],
    });
    render(<Match state={state} refresh={vi.fn()} />);

    expect(screen.getByText("1位の回答を待っています…")).toBeInTheDocument();
    expect(screen.getByText(/2\. ホスト/)).toBeInTheDocument();
  });
});
