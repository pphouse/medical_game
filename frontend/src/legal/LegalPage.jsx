import { Link } from "react-router-dom";
import { legalDoc } from "./documents";

/** 規約類のページ（/terms, /privacy など）。ログイン前でも読める。
 * App Store Connect にはプライバシーポリシーの URL を登録している。 */
export default function LegalPage({ docKey }) {
  const { title, updated, Body } = legalDoc(docKey);
  return (
    <div className="screen legal-screen">
      <Link className="back-link" to="/">
        ← 戻る
      </Link>
      <h1>{title}</h1>
      <p className="legal-updated">最終更新日: {updated}</p>
      <div className="mypage-card legal-card">
        <Body />
      </div>
    </div>
  );
}
