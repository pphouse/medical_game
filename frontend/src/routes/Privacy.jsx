import { Link } from "react-router-dom";

// 事業者名と連絡先は環境ごとに変わるので env から入れる。iOS ビルドでは
// scripts/check-native-env.mjs が未設定を弾く（連絡先の無いプライバシー
// ポリシーは App Store の審査で通らない）。
const OPERATOR = import.meta.env.VITE_OPERATOR_NAME || "";
const CONTACT = import.meta.env.VITE_CONTACT_EMAIL || "";

const UPDATED = "2026年9月7日";

/** プライバシーポリシー。App Store Connect にはこのページの URL を登録する。 */
export default function Privacy() {
  return (
    <div className="screen legal-screen">
      <Link className="back-link" to="/">
        ← 戻る
      </Link>
      <h1>プライバシーポリシー</h1>
      <p className="legal-updated">最終更新日: {UPDATED}</p>

      <div className="mypage-card legal-card">
        <h2>1. 取得する情報</h2>
        <ul>
          <li>
            <strong>アカウント情報</strong>: メールアドレス、表示名。
            任意で大学名と学年。
          </li>
          <li>
            <strong>学習の記録</strong>: 解答した問題、正誤、解答にかかった時間、
            自己評価（◎○△✕）、復習の予定。
          </li>
          <li>
            <strong>成績</strong>: 模擬試験の結果、ランキング、対戦の記録。
          </li>
          <li>
            <strong>学生証の画像</strong>: 学生認証を申請した場合のみ。
            審査のためだけに使い、却下時はただちに、承認時は90日以内に削除します。
          </li>
          <li>
            <strong>通知の購読情報</strong>: 復習リマインドを有効にした場合のみ。
          </li>
        </ul>
        <p>
          広告や行動追跡のための情報は取得しません。第三者の広告ネットワークや
          解析サービスは組み込んでいません。
        </p>

        <h2>2. 利用目的</h2>
        <ul>
          <li>出題・採点・復習スケジュールの計算など、アプリの機能の提供</li>
          <li>ランキング、大学対抗、偏差値などの集計</li>
          <li>学生認証の審査</li>
          <li>不正利用・不適切な投稿への対応</li>
        </ul>

        <h2>3. 第三者への提供</h2>
        <p>
          本人の同意なく第三者に提供・販売することはありません。
          サービスの運営に必要な範囲で、次の事業者のインフラを利用しています。
        </p>
        <ul>
          <li>Supabase（認証・データベース・画像保管）</li>
          <li>Vercel（アプリの配信）</li>
        </ul>

        <h2>4. 保存期間と削除</h2>
        <p>
          アカウントが存在する間、情報を保存します。
          <strong>アプリ内の「マイページ → アカウントを削除」から、いつでも
          ご自身で削除できます。</strong>
          削除するとプロフィール・解答履歴・復習予定・模試の結果・対戦の記録は
          復元できない形で消去され、ログインに使うアカウントそのものも削除されます。
        </p>
        <p>
          ただし、あなたが作成して公開された問題は、作成者の表示を外したうえで
          残ります。その問題を解いている他の利用者の学習記録を壊さないためです。
        </p>

        <h2>5. 医療情報についての注意</h2>
        <p>
          本アプリは医学生の試験対策を目的とした学習用サービスです。
          収録している問題・解説は医療行為の助言ではなく、診断や治療の判断に
          用いることはできません。
        </p>

        <h2>6. 年齢について</h2>
        <p>
          13歳未満の方の利用は想定していません。
        </p>

        <h2>7. 本ポリシーの変更</h2>
        <p>
          内容を変更する場合は、このページの最終更新日を改めたうえで掲載します。
        </p>

        {(OPERATOR || CONTACT) && (
          <>
            <h2>8. お問い合わせ</h2>
            {OPERATOR && <p>運営者: {OPERATOR}</p>}
            {CONTACT && (
              <p>
                連絡先: <a href={`mailto:${CONTACT}`}>{CONTACT}</a>
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
