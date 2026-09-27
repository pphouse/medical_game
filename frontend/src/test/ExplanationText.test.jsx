import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ExplanationText from "../components/ExplanationText";

/** 本番に入っている取り込み当初の形式。URLが独立した行にある。 */
const OLD_FORMAT = [
  "正答は A「膵の萎縮を認める。」。",
  "",
  "この設問は医師国家試験の過去問です。詳しい解説は準備中で、内容の確認後に順次追加されます。",
  "",
  "出典：厚生労働省ホームページ 第119回医師国家試験 A001",
  "https://www.mhlw.go.jp/seisakunitsuite/bunya/kenkou_iryou/iryou/topics/tp250428-01.html",
  "（設問文および選択肢は本アプリの表示形式に整形しています）",
].join("\n");

/** 解説を入れたあとの形式。URLは出典行の括弧の中にある。 */
const NEW_FORMAT = [
  "正答は A「膵の萎縮を認める。」。",
  "",
  "自己免疫性膵炎では膵がびまん性に腫大し、いわゆるソーセージ様の形態を示す。",
  "",
  "【誤答選択肢の解説】",
  "B「高齢男性に好発する。」: 60歳代以降の男性に多い。",
  "",
  "※この解説はアプリ編集部が作成したものです。厚生労働省が公表する過去問には解説は含まれません。",
  "",
  "出典：厚生労働省ホームページ 第119回医師国家試験 A001（https://www.mhlw.go.jp/x.html）／設問文および選択肢を本アプリの表示形式に整形",
].join("\n");

describe("ExplanationText", () => {
  it("生のURLは短い文言のリンクにする", () => {
    // URLをそのまま出すと1段落を丸ごと占めて、解説本文より目立っていた。
    const { container } = render(<ExplanationText text={NEW_FORMAT} />);
    const link = screen.getByRole("link", { name: "公表ページ" });
    expect(link).toHaveAttribute("href", "https://www.mhlw.go.jp/x.html");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(container.textContent).not.toContain("https://www.mhlw.go.jp/x.html");
  });

  it("出典と免責は本文と分けて下にまとめる", () => {
    const { container } = render(<ExplanationText text={NEW_FORMAT} />);
    const note = container.querySelector(".explanation-note");
    expect(note.textContent).toContain("※この解説はアプリ編集部が作成した");
    expect(note.textContent).toContain("出典：厚生労働省ホームページ");
    // 解説本体は注記の外に残る。
    expect(note.textContent).not.toContain("自己免疫性膵炎");
    expect(container.textContent).toContain("自己免疫性膵炎");
  });

  it("URLが別行にある古い形式でも注記側へ送る", () => {
    // 本番DBにはこの形式が残っている。出典の3行がひと続きで下に行くこと。
    const { container } = render(<ExplanationText text={OLD_FORMAT} />);
    const note = container.querySelector(".explanation-note");
    expect(note.textContent).toContain("出典：厚生労働省ホームページ");
    expect(note.textContent).toContain("設問文および選択肢は本アプリの表示形式に整形");
    expect(screen.getByRole("link", { name: "公表ページ" })).toBeInTheDocument();
    expect(note.textContent).not.toContain("正答は A");
  });

  it("複数のURLをそれぞれリンクにする", () => {
    const text = "出典：https://a.example/1 と https://b.example/2";
    render(<ExplanationText text={text} />);
    const links = screen.getAllByRole("link", { name: "公表ページ" });
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://a.example/1",
      "https://b.example/2",
    ]);
  });

  it("空のときは何も出さない", () => {
    const { container } = render(<ExplanationText text="" />);
    expect(container.firstChild).toBeNull();
  });
});
