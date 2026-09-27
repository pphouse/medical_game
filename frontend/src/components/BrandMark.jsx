import characterUrl from "../assets/character.png";

/** アプリのロゴマーク（医トレ）。ホーム画面の先頭に置く。
 *
 * マークはアプリアイコンと同じキャラクター（白衣のフクロウ）。アイコンから
 * 背景を抜いた画像を使うので、ホーム画面に並ぶアイコンと同じ顔が出る
 * （frontend/scripts/extract-character.py で書き出す）。 */
export default function BrandMark() {
  return (
    <div className="brand-mark" aria-label="医トレ">
      <img className="brand-mark-icon" src={characterUrl} alt="" aria-hidden="true" />
      <span className="brand-mark-name">医トレ</span>
    </div>
  );
}
