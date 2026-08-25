import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Match from "../routes/Battle/Match";
import Room from "../routes/Battle/Room";

vi.mock("../lib/supabase", () => ({ supabase: null, isSupabaseConfigured: false }));
vi.mock("../api", () => ({
  api: {
    battleState: vi.fn(),
    battleStart: vi.fn(),
    battleResult: vi.fn(),
    battleLeave: vi.fn(),
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

/** Match は開幕のVS演出を挟むので、本編が出るまでタイマーを進める。 */
function renderMatch(state, refresh = vi.fn()) {
  const result = render(<Match state={state} refresh={refresh} onLeave={vi.fn()} />, {
    wrapper: MemoryRouter,
  });
  act(() => {
    vi.advanceTimersByTime(2500);
  });
  return result;
}

const WAITING = {
  room: { room_code: "123456", status: "waiting", question_count: 10 },
  participants: [
    { profile_id: "me", display_name: "ホスト", is_host: true, is_me: true, connected: true },
  ],
};

function inProgress(roundOverrides = {}, extra = {}) {
  return {
    room: { room_code: "123456", status: "in_progress", question_count: 10 },
    participants: [
      {
        profile_id: "me",
        display_name: "ホスト",
        university: "A大学",
        tier: "B",
        hp: 100,
        is_host: true,
        is_me: true,
        connected: true,
        score: 100,
      },
      {
        profile_id: "opp",
        display_name: "相手",
        university: "B大学",
        tier: "A",
        hp: 80,
        is_host: false,
        is_me: false,
        connected: true,
        score: 80,
      },
    ],
    last_result: null,
    round: {
      id: 7,
      number: 2,
      total: 10,
      closes_at: new Date(Date.now() + 30_000).toISOString(),
      i_have_answered: false,
      answered_profile_ids: [],
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
    ...extra,
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

  it("finished: 結果画面（順位とHP）を表示する", async () => {
    api.battleState.mockResolvedValue({
      room: { room_code: "123456", status: "finished", question_count: 10 },
      participants: [],
    });
    api.battleResult.mockResolvedValue({
      standings: [
        { rank: 1, display_name: "ホスト", is_me: true, score: 320, hp: 90, correct_count: 4 },
        { rank: 2, display_name: "相手", is_me: false, score: 180, hp: 0, correct_count: 2 },
      ],
    });

    renderRoom();

    expect(await screen.findByText("対戦結果")).toBeInTheDocument();
    expect(screen.getByText("正解 4問")).toBeInTheDocument();
    // 対戦後も他のメニューへ移動できる導線があること
    expect(screen.getByRole("link", { name: "ホームに戻る" })).toBeInTheDocument();
  });
});

describe("対戦ラウンド内の状態 (Match)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("VSヘッダーに双方の名前・大学・ランク・HPを常に表示する", () => {
    renderMatch(inProgress());

    expect(screen.getByText("ホスト")).toBeInTheDocument();
    expect(screen.getByText("A大学")).toBeInTheDocument();
    expect(screen.getByText("相手")).toBeInTheDocument();
    expect(screen.getByText("B大学")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("選択肢を選んでから回答ボタンを押すと回答が送られる（早押しは無い）", async () => {
    api.battleAnswer.mockResolvedValue({});
    const refresh = vi.fn().mockResolvedValue();
    renderMatch(inProgress(), refresh);

    expect(screen.queryByRole("button", { name: "早押し！" })).not.toBeInTheDocument();

    // 未選択のうちは回答できない
    expect(screen.getByRole("button", { name: "選択肢を選んでください" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /利尿薬/ }));
    const submit = screen.getByRole("button", { name: "A で回答する" });
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    // フェイクタイマー下では waitFor が進まないので、マイクロタスクを流す。
    await act(async () => {});
    expect(api.battleAnswer).toHaveBeenCalledWith(7, "A");
    expect(refresh).toHaveBeenCalled();
  });

  it("回答済みなら相手待ちの表示になり、選択肢は押せない", () => {
    renderMatch(inProgress({ i_have_answered: true, answered_profile_ids: ["me"] }));

    expect(screen.getByText("相手の回答を待っています…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /利尿薬/ })).toBeDisabled();
  });

  it("相手が先に回答済みだと急かす表示が出る", () => {
    renderMatch(inProgress({ answered_profile_ids: ["opp"] }));

    expect(screen.getByText("相手は回答済み！急いで！")).toBeInTheDocument();
  });

  it("被弾するとダメージ量を表示する", () => {
    renderMatch(
      inProgress(
        {},
        {
          last_result: {
            number: 1,
            correct_choice_key: "A",
            reason: "wrong_answer",
            damage: { me: 20 },
            my_damage: 20,
          },
        }
      )
    );

    expect(screen.getByText("-20%")).toBeInTheDocument();
  });
});
