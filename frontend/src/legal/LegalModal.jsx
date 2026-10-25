import { useEffect } from "react";
import { legalDoc } from "./documents";

/** 規約類を画面の上に重ねて読む。同意画面や解説から開き、閉じると元の画面に
 * そのまま戻る（ページ遷移にすると、解いている途中の問題が消える）。 */
export default function LegalModal({ docKey, onClose }) {
  const doc = legalDoc(docKey);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!doc) return null;
  const { Body } = doc;
  return (
    <div className="legal-modal-backdrop" onClick={onClose}>
      <div
        className="legal-modal"
        role="dialog"
        aria-modal="true"
        aria-label={doc.title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="legal-modal-head">
          <h2>{doc.title}</h2>
          <button type="button" className="legal-modal-close" onClick={onClose}>
            閉じる
          </button>
        </div>
        <div className="legal-modal-body legal-card">
          <p className="legal-updated">最終更新日: {doc.updated}</p>
          <Body />
        </div>
      </div>
    </div>
  );
}
