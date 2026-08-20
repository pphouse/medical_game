const VALID_TIERS = new Set(["SS", "S", "A", "B", "C", "D"]);

/** 対戦・模試ランクの色付きバッジ（SS=金, S=銀, A=銅, B=青, C=黄, D=灰）。 */
export default function TierBadge({ tier, fallback = "未ランク", large = false }) {
  if (!tier || !VALID_TIERS.has(tier)) {
    return <span className="tier-pill tier-none">{fallback}</span>;
  }
  return (
    <span className={`tier-pill tier-${tier}${large ? " tier-pill-lg" : ""}`}>{tier}</span>
  );
}
