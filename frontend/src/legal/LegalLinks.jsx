import { useState } from "react";
import { LEGAL_DOCS } from "./documents";
import LegalModal from "./LegalModal";

/** 規約類へのリンクの並び（マイページ・ログイン画面の下）。 */
export default function LegalLinks() {
  const [open, setOpen] = useState(null);
  return (
    <div className="legal-links">
      {LEGAL_DOCS.map((doc) => (
        <button
          key={doc.key}
          type="button"
          className="mypage-legal-link"
          onClick={() => setOpen(doc.key)}
        >
          {doc.title}
        </button>
      ))}
      {open && <LegalModal docKey={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
