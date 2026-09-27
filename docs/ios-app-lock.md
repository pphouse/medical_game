# アプリのロック（フェーズ2・iOS のみ）

1日の目標の問題数を解くまで、本人が選んだアプリ（TikTok・YouTube・X など）を
ロックする。Apple の Screen Time API（FamilyControls / ManagedSettings /
DeviceActivity）を使う。Opal や one sec と同じ仕組み。

目標・連続記録・通知（フェーズ1）はこの機能が無くても動く。ロックは
「目標を達成するまで」の判定をフェーズ1の仕組みから借りる。

## できること・できないこと

- ロックできるのは iOS アプリだけ。Web 版からは他のアプリを止められない。
- ロックするアプリは本人が Apple の選択画面（FamilyActivityPicker）で選ぶ。
  アプリ側からは「TikTok」と決め打ちできず、何が選ばれたかも分からない
  （中身の見えないトークンで受け取る）。Safari で開く抜け道は、サイトや
  「SNS」などのカテゴリごと選べば塞げる。
- 本人の端末を本人が制限する `.individual` の許可を使う。iOS 16 以降。
  アプリ本体の対応 OS は 15 のまま、ロックの設定だけ 16 以降で出す。
- 本人は設定からいつでも許可を外せる。自分との約束を支える仕組みで、
  完全な強制ではない。
- 動作の確認は実機の iPhone でする（シミュレーターでは Screen Time の
  制限を正しく試せない）。

## Apple への申請（配布用の権限）

開発中は自分の iPhone で試せるが、TestFlight / App Store で配るには
Apple から Family Controls の配布用の権限をもらう必要がある。許可まで
日数がかかるので、実装より先に出しておく。

1. Apple Developer に、チームの Account Holder（登録した本人）のアカウントで
   サインインする
2. 申請ページを開く:
   https://developer.apple.com/contact/request/family-controls-distribution
3. 下の「バンドル ID」と「貼る英文」を、フォームの合う欄に貼る
   （欄の名前や並びは変わることがある）
4. 返事はメールで来る。許可が出ると、Certificates, Identifiers & Profiles の
   各 App ID で Family Controls を有効にできるようになる

### バンドル ID

拡張機能も Screen Time API を使うので、4つとも権限が要る。

| 役割 | バンドル ID |
|---|---|
| アプリ本体 | `jp.pphouse.medquiz` |
| 毎朝ロックを掛け直す（DeviceActivityMonitor） | `jp.pphouse.medquiz.DeviceActivityMonitor` |
| ロック画面の文言（ShieldConfiguration） | `jp.pphouse.medquiz.ShieldConfiguration` |
| ロック画面のボタン（ShieldAction） | `jp.pphouse.medquiz.ShieldAction` |

### 貼る英文

```
App: 医トレ (currently shown as "CBT国試クイズ" on the home screen)
Bundle IDs:
- jp.pphouse.medquiz (app)
- jp.pphouse.medquiz.DeviceActivityMonitor (device activity monitor extension)
- jp.pphouse.medquiz.ShieldConfiguration (shield configuration extension)
- jp.pphouse.medquiz.ShieldAction (shield action extension)

What the app is:
A question-bank app for Japanese medical students preparing for the CBT
and the National Medical Licensing Examination. Users set their own daily
goal (for example, 10 questions a day) and track their streak.

How we will use Family Controls:
We are adding an optional, opt-in "study lock" that helps users build a
daily study habit. The user chooses, with the system FamilyActivityPicker,
which of their own apps, categories or websites (typically social media
and video apps) should be shielded until they finish their daily goal.

- FamilyControls: AuthorizationCenter with .individual authorization only.
  The user restricts their own device; there is no parent/child use.
- ManagedSettings: a shield is applied to the selected tokens at the start
  of each day and removed as soon as the user completes the day's goal in
  our app. An emergency unlock (once a day, after a short wait) is always
  available so the user is never locked out of something they need.
- DeviceActivity: a daily repeating schedule; the DeviceActivityMonitor
  extension re-applies the shield each morning even if our app is not
  running.
- ShieldConfiguration / ShieldAction extensions: the shield tells the user
  how many questions are left and sends a notification that opens our app.

Privacy:
The selected application, category and web domain tokens stay on the
device (in an App Group container shared only with our extensions). We
never send them to our servers, never try to identify which apps were
chosen, and do not collect any Screen Time usage data. The feature is off
by default, and the user can turn it off in the app or revoke access in
Settings at any time.
```

## 実装の予定

- ネイティブ側は Capacitor のプラグイン（Swift）と拡張機能3つ。Xcode での
  ターゲットの追加（File → New → Target）は Mac で行う。Swift のコードは
  リポジトリに置く。
- 本体と拡張機能は App Group `group.jp.pphouse.medquiz` で、選んだアプリの
  トークン・今日の目標・解いた数を共有する（App Group も Identifiers で登録する）。
- 流れ: 毎朝決まった時刻に DeviceActivityMonitor がロックを掛ける →
  アプリで目標を達成すると本体がロックを外す → 翌朝また掛かる。
- 解いた数はサーバで数える（PC で解いた分も入る）。ロックが外れるのは
  iPhone のアプリを開いたとき。
- ロック画面のボタンから直接アプリは開けないので、通知を出してタップしてもらう。
- 緊急解除は1日1回、待ち時間つき。
