/** Temporary screen for routes whose feature ships in a later phase. */
export default function Placeholder({ title, phase }) {
  return (
    <div className="screen">
      <h2>{title}</h2>
      <div className="empty-card">この機能は{phase}で実装されます。</div>
    </div>
  );
}
