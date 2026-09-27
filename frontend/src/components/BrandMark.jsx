/** アプリのロゴマーク（医トレ）。ホーム画面の先頭に置く。
 *
 * 画像ファイルではなく文字と図形で組む。端末の解像度で潰れないうえ、
 * ダークモードでも配色トークンだけで追従できる。 */
export default function BrandMark() {
  return (
    <div className="brand-mark" aria-label="医トレ">
      <span className="brand-mark-icon" aria-hidden="true">
        医
      </span>
      <span className="brand-mark-name">医トレ</span>
    </div>
  );
}
