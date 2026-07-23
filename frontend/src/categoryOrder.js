export const CATEGORY_ORDER = [
  "基礎医学", "公衆衛生", "臨床医学総論", "循環器", "呼吸器", "消化器", "腎臓",
  "内分泌代謝", "神経", "血液", "免疫", "感染症", "中毒・環境異常症", "救急",
  "小児", "産科", "婦人科", "泌尿器", "眼科", "耳鼻咽喉科", "皮膚", "精神",
  "整形", "麻酔", "放射線", "多選択肢", "四連問",
];

export function sortByCategoryOrder(items, getCategory = (item) => item.category) {
  return [...items].sort(
    (a, b) => CATEGORY_ORDER.indexOf(getCategory(a)) - CATEGORY_ORDER.indexOf(getCategory(b))
  );
}
