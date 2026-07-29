// カテゴリ → 配色テーマ (§5-11: CBT 出題基準の area D-1〜D-15, E, F に対応)。
//
// LLM 生成パイプラインは category に出題基準の area_title（例 "循環器系"、
// "腎・尿路系（体液・電解質バランスを含む）"）を入れるため、完全一致では
// なく部分一致ルールで解決する。既存シードの5分野（"循環器" など）も同じ
// ルールに一致する。キーは App.css の .theme-* と対応。
const RULES = [
  // D-1〜D-15（人体各器官の正常構造と機能、病態、診断、治療）
  { match: "血液", letter: "血", key: "rose" },
  { match: "リンパ", letter: "血", key: "rose" },
  { match: "神経", letter: "神", key: "violet" },
  { match: "皮膚", letter: "皮", key: "amber" },
  { match: "運動器", letter: "運", key: "mint" },
  { match: "筋骨格", letter: "運", key: "mint" },
  { match: "循環器", letter: "循", key: "rose" },
  { match: "呼吸器", letter: "呼", key: "sky" },
  { match: "消化器", letter: "消", key: "amber" },
  { match: "腎", letter: "腎", key: "sky" },
  { match: "尿路", letter: "腎", key: "sky" },
  { match: "生殖", letter: "生", key: "rose" },
  { match: "妊娠", letter: "産", key: "rose" },
  { match: "分娩", letter: "産", key: "rose" },
  { match: "乳房", letter: "乳", key: "rose" },
  { match: "内分泌", letter: "内", key: "mint" },
  { match: "代謝", letter: "内", key: "mint" },
  { match: "栄養", letter: "内", key: "mint" },
  { match: "眼", letter: "眼", key: "sky" },
  { match: "視覚", letter: "眼", key: "sky" },
  { match: "耳鼻", letter: "耳", key: "amber" },
  { match: "咽喉", letter: "耳", key: "amber" },
  { match: "口腔", letter: "耳", key: "amber" },
  { match: "精神", letter: "精", key: "violet" },
  { match: "産婦", letter: "産", key: "rose" },
  { match: "小児", letter: "小", key: "amber" },
  { match: "泌尿器", letter: "泌", key: "sky" },
  // E（全身におよぶ生理的変化、病態、診断、治療）
  { match: "感染", letter: "感", key: "mint" },
  { match: "腫瘍", letter: "腫", key: "violet" },
  { match: "免疫", letter: "免", key: "mint" },
  { match: "アレルギー", letter: "免", key: "mint" },
  { match: "救急", letter: "救", key: "rose" },
  { match: "中毒", letter: "救", key: "rose" },
  { match: "全身", letter: "全", key: "violet" },
  // F（診療の基本）
  { match: "症候", letter: "症", key: "sky" },
  { match: "診察", letter: "診", key: "sky" },
  { match: "診療", letter: "診", key: "sky" },
  { match: "検査", letter: "検", key: "amber" },
  // A〜C（基本事項・社会と医学・医療・医学一般）
  { match: "資質", letter: "基", key: "slate" },
  { match: "社会", letter: "社", key: "slate" },
  { match: "医学一般", letter: "般", key: "slate" },
];

const FALLBACK = { letter: "他", key: "slate" };

export function getCategoryTheme(category) {
  if (!category) return FALLBACK;
  for (const rule of RULES) {
    if (category.includes(rule.match)) {
      return { letter: rule.letter, key: rule.key };
    }
  }
  return { letter: category[0], key: "slate" };
}
