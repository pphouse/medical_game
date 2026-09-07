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

  it("waiting: コードの共有と、ロビーに戻るとリセットされる旨を伝える", async () => {
    api.battleState.mockResolvedValue({
      room: { room_code: "123456", status: "waiting", question_count: 10 },
      participants: [{ display_name: "ホスト", is_host: true, is_me: true, connected: true }],
    });

    renderRoom();

    expect(await screen.findByText("このコードを友達に共有してください。")).toBeInTheDocument();
    expect(
      screen.getByText("※対戦ロビーに戻るとコードはリセットされます"),
    ).toBeInTheDocument();
  });

  it("finished: 勝敗バナーとHP・ランクの増減を表示する", async () => {
    api.battleState.mockResolvedValue({
      room: { room_code: "123456", status: "finished", question_count: 10 },
      participants: [],
    });
    api.battleResult.mockResolvedValue({
      standings: [
        {
          rank: 1,
          display_name: "ホスト",
          university: "A大学",
          is_me: true,
          score: 320,
          hp: 90,
          correct_count: 4,
        },
        {
          rank: 2,
          display_name: "相手",
          university: "B大学",
          is_me: false,
          score: 180,
          hp: 0,
          correct_count: 2,
        },
      ],
      rank: {
        before: { tier: "C", progress: 80, points: 180 },
        after: { tier: "C", progress: 92, points: 192, next_tier: "B" },
        delta: 12,
        promoted: false,
        demoted: false,
      },
    });

    renderRoom();

    expect(await screen.findByText("WIN!")).toBeInTheDocument();
    expect(screen.getByText("正解 4問")).toBeInTheDocument();
    expect(screen.getByText("+12 pt")).toBeInTheDocument();
    // 対戦後も他のメニューへ移動できる導線があること
    expect(screen.getByRole("link", { name: "ホームに戻る" })).toBeInTheDocument();
  });

  it("finished: 出題された問題の正誤一覧を出し、クリックで解説を開く", async () => {
    api.battleState.mockResolvedValue({
      room: { room_code: "123456", status: "finished", question_count: 10 },
      participants: [],
    });
    api.battleResult.mockResolvedValue({
      standings: [
        { rank: 1, display_name: "ホスト", is_me: true, score: 1, hp: 100, correct_count: 1 },
        { rank: 2, display_name: "相手", is_me: false, score: 0, hp: 0, correct_count: 0 },
      ],
      rank: { before: null, after: {}, delta: 0, promoted: false, demoted: false },
      questions: [
        {
          round_number: 1,
          question_id: 11,
          category: "循環器",
          exam_type: "CBT",
          case_stem: null,
          question_text: "正解した問題",
          choices: [
            { key: "A", text: "あ" },
            { key: "B", text: "い" },
          ],
          correct_choice_key: "A",
          explanation: "正解の解説文",
          answered: true,
          selected_choice_key: "A",
          correct: true,
        },
        {
          round_number: 2,
          question_id: 12,
          category: "消化器",
          exam_type: "CBT",
          case_stem: null,
          question_text: "間違えた問題",
          choices: [
            { key: "A", text: "あ" },
            { key: "B", text: "い" },
          ],
          correct_choice_key: "B",
          explanation: "不正解の解説文",
          answered: true,
          selected_choice_key: "A",
          correct: false,
        },
      ],
    });

    renderRoom();

    expect(await screen.findByText("出題された問題（1/2問 正解）")).toBeInTheDocument();
    // 正誤が一覧の時点で分かること
    const rows = screen.getAllByRole("button", { expanded: false });
    const wrong = rows.find((b) => b.textContent.includes("間違えた問題"));
    expect(wrong.textContent).toContain("✕");
    expect(rows.find((b) => b.textContent.includes("正解した問題")).textContent).toContain("○");

    // 開くまで解説は出さない
    expect(screen.queryByText("不正解の解説文")).not.toBeInTheDocument();
    fireEvent.click(wrong);
    expect(screen.getByText("不正解の解説文")).toBeInTheDocument();
    expect(screen.getByText("あなたの解答")).toBeInTheDocument();
  });

  it("finished: 昇格したときは RANK UP! を出す", async () => {
    api.battleState.mockResolvedValue({
      room: { room_code: "123456", status: "finished", question_count: 10 },
      participants: [],
    });
    api.battleResult.mockResolvedValue({
      standings: [
        { rank: 1, display_name: "ホスト", is_me: true, score: 1, hp: 100, correct_count: 5 },
        { rank: 2, display_name: "相手", is_me: false, score: 0, hp: 0, correct_count: 1 },
      ],
      rank: {
        before: { tier: "C", progress: 95, points: 195 },
        after: { tier: "B", progress: 8, points: 208, next_tier: "A" },
        delta: 13,
        promoted: true,
        demoted: false,
      },
    });

    renderRoom();

    expect(await screen.findByText("RANK UP!")).toBeInTheDocument();
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

  it("回答すると相手を待たずにすぐ自分の正誤が分かる", async () => {
    api.battleAnswer.mockResolvedValue({ correct: true, correct_choice_key: "A" });
    const refresh = vi.fn().mockResolvedValue();
    renderMatch(inProgress(), refresh);

    fireEvent.click(screen.getByRole("button", { name: /利尿薬/ }));
    fireEvent.click(screen.getByRole("button", { name: "A で回答する" }));
    await act(async () => {});

    expect(screen.getByText("○ 正解！")).toBeInTheDocument();
    // 相手の判定を待たずに表示されている（refresh の結果を待つ必要が無い）。
    expect(screen.getByRole("button", { name: /利尿薬/ })).toHaveClass("correct");
  });

  it("不正解のときは選んだ選択肢と正解の選択肢がそれぞれ分かる", async () => {
    api.battleAnswer.mockResolvedValue({ correct: false, correct_choice_key: "B" });
    renderMatch(inProgress());

    fireEvent.click(screen.getByRole("button", { name: /利尿薬/ }));
    fireEvent.click(screen.getByRole("button", { name: "A で回答する" }));
    await act(async () => {});

    expect(screen.getByText("✕ 不正解…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /利尿薬/ })).toHaveClass("incorrect");
    expect(screen.getByRole("button", { name: /抗菌薬/ })).toHaveClass("correct");
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
