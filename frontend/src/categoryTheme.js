const THEMES = {
  循環器: { letter: "循", key: "rose" },
  呼吸器: { letter: "呼", key: "sky" },
  消化器: { letter: "消", key: "amber" },
  内分泌代謝: { letter: "内", key: "mint" },
  神経: { letter: "神", key: "violet" },
};

const FALLBACK = { letter: "他", key: "slate" };

export function getCategoryTheme(category) {
  return THEMES[category] ?? FALLBACK;
}
