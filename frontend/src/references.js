// 問題と解説の出典・参考文献。解説の下（ExplanationText）と「出典・参考文献」
// ページ（/sources）の両方で同じ一覧を出す。
//
// App Store 審査（Guideline 1.4.1）で、医療情報には見つけやすい出典が要ると
// 指摘されたために置いている。URL を足すときは、実際に開けることを確かめる。

/** 国試の出典行（「出典：厚生労働省ホームページ 第116回…」）に添える公表ページ。 */
export const MHLW_EXAM_URL = "https://www.mhlw.go.jp/topics/2005/10/tp1028-3/index.html";

export const REFERENCE_GROUPS = [
  {
    title: "問題の出典",
    items: [
      {
        label: "厚生労働省「医師等国家試験問題及び解答について」",
        note: "医師国家試験の問題・正答（各問題の解説に回と問題番号を記載）",
        url: MHLW_EXAM_URL,
      },
      {
        label: "厚生労働省「医師国家試験の施行について」",
        url: "https://www.mhlw.go.jp/kouseiroudoushou/shikaku_shiken/ishi/",
      },
      {
        label: "公益社団法人 医療系大学間共用試験実施評価機構（CATO）",
        note: "CBT 形式の問題は、本アプリが出題範囲に沿って作成したオリジナル問題です",
        url: "https://www.cato.or.jp/",
      },
    ],
  },
  {
    title: "出題範囲の基準",
    items: [
      {
        label: "厚生労働省「令和6年版医師国家試験出題基準」",
        url: "https://www.mhlw.go.jp/stf/shingi2/0000128981_00001.html",
      },
      {
        label: "文部科学省「医学教育モデル・コア・カリキュラム」",
        url: "https://www.mext.go.jp/a_menu/koutou/iryou/mext_00005.html",
      },
    ],
  },
  {
    title: "解説の根拠（診療ガイドラインなど）",
    items: [
      {
        label: "Minds ガイドラインライブラリ（日本医療機能評価機構）",
        url: "https://minds.jcqhc.or.jp/",
      },
      {
        label: "日本循環器学会 ガイドラインシリーズ",
        url: "https://www.j-circ.or.jp/guideline/guideline-series/",
      },
      {
        label: "日本消化器病学会 ガイドライン",
        url: "https://www.jsge.or.jp/committees/guideline/guideline/",
      },
      {
        label: "日本呼吸器学会 ガイドライン",
        url: "https://www.jrs.or.jp/publication/jrs_guidelines/",
      },
      {
        label: "日本糖尿病学会「糖尿病診療ガイドライン2024」",
        url: "https://www.jds.or.jp/modules/publication/index.php?content_id=4",
      },
      {
        label: "日本感染症学会 ガイドライン・提言",
        url: "https://www.kansensho.or.jp/modules/guidelines/",
      },
      {
        label: "国立がん研究センター がん情報サービス",
        url: "https://ganjoho.jp/",
      },
      {
        label: "医薬品医療機器総合機構（PMDA） 医療用医薬品の添付文書情報",
        url: "https://www.pmda.go.jp/",
      },
      {
        label: "e-Gov 法令検索（医療関係法規）",
        url: "https://laws.e-gov.go.jp/",
      },
    ],
  },
];

export const MEDICAL_DISCLAIMER =
  "解説は医学生の試験対策のための学習用です。実際の診療では、最新の診療ガイドラインや添付文書を確認してください。";
