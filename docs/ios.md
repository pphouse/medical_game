# iOS アプリ（Capacitor）

React のフロントエンドをそのまま iOS アプリとして配布するための手順。
Web 版と**同じコード・同じバックエンド**が動く。iOS 専用の分岐は
`frontend/src/native.js` / `frontend/src/nativeBootstrap.js` に閉じている。

```
frontend/
  capacitor.config.json   アプリID・表示名・起動画面などの設定
  assets/                 アイコンの元データ（SVG）
  ios/App/                Xcode プロジェクト（コミット済み。cap sync で更新される）
  scripts/check-native-env.mjs   ビルド時に接続先の設定漏れを落とすチェック
```

## 0. 何が必要か

| もの | 必要な場面 | 補足 |
|---|---|---|
| Apple Developer Program（年 $99） | 実機テスト・TestFlight・審査提出 | 登録に数日〜1週間かかることがあるので先に始める |
| Mac + Xcode 16 以降 | ビルド・署名・提出 | **これだけは macOS でしか動かない**（Apple の制約） |
| Node.js 22+ | Web 側のビルドと `cap sync` | Linux / Windows でも動く |

Capacitor 8 は CocoaPods ではなく Swift Package Manager を使うので、
`npm run ios:sync` までは **Mac 以外でも完結する**。Mac が要るのは
Xcode を開いてからだけ。

## 1. 接続先の設定（最重要）

アプリの中身は `capacitor://localhost` から動く。Web 版の既定である相対パスの
`/api` はアプリ自身のバンドルを指してしまうため、**バックエンドの絶対 URL を
ビルド時に埋め込む必要がある**。埋め忘れたまま端末に入れると、通信が全部失敗する。

`frontend/.env.production` を作る（このファイルはコミットしない）:

```sh
VITE_API_BASE_URL=https://<バックエンドのドメイン>/api
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>
```

`npm run build:ios` は上の3つが揃っていて、API が `https://` で始まることを
確認してからビルドする（`scripts/check-native-env.mjs`）。足りなければ
その場で落ちるので、設定漏れのまま端末に入ることはない。

バックエンド側の CORS は対応済み。`capacitor://localhost` は
`backend/config/settings.py` の `NATIVE_APP_ORIGINS` で常に許可している
（環境変数では足せないため）。

## 2. Supabase 側の設定

メールのリンク（マジックリンク・登録確認）は、Web ではブラウザに戻るが、
アプリでは**カスタム URL スキームでアプリを開き直す**形で戻る。
Supabase ダッシュボードの **Authentication → URL Configuration → Redirect URLs**
に次を追加する:

```
jp.pphouse.medquiz://auth-callback
```

この文字列は3か所で一致している必要がある:

- `frontend/src/native.js` の `DEEP_LINK_SCHEME`
- `frontend/ios/App/App/Info.plist` の `CFBundleURLTypes`
- Supabase の Redirect URLs

戻ってきた URL は `frontend/src/lib/deepLink.js` が処理し、PKCE の `code` と
implicit の `access_token` のどちらでもログインを完了できる。

## 3. ビルドする（Mac 以外でもここまで）

```sh
cd frontend
npm ci
npm run ios:sync      # build:ios（設定チェック込み）→ cap sync ios
```

`ios/App/App/public` に Web の成果物が入り、`Package.swift` にプラグインが
反映される。ここまでは Linux でも動く。

## 4. Xcode で開く（ここから Mac）

```sh
cd frontend
npm run ios:open      # Xcode で ios/App/App.xcodeproj が開く
```

Xcode でやること:

1. **Signing & Capabilities** → Team に自分の Apple Developer チームを選ぶ。
2. **Bundle Identifier** を自分のものに変える（既定は `jp.pphouse.medquiz`）。
   変えた場合は `capacitor.config.json` の `appId`、`Info.plist` の
   `CFBundleURLTypes`、`src/native.js` の `DEEP_LINK_SCHEME`、Supabase の
   Redirect URLs も**同じ値に揃える**。
3. **General → Minimum Deployments** を確認（Capacitor 8 は iOS 14+）。
4. 実機を選んで ▶︎ で起動。TestFlight に上げるなら
   Product → Archive → Distribute App。

コードを直したあとは、毎回 `npm run ios:sync` してから Xcode を再ビルドする。
`ios/App/App/public` は生成物なので直接いじらない。

## 5. アイコンと起動画面

元データは `frontend/assets/*.svg`。作り直すときは:

```sh
cd frontend
npm run ios:assets    # assets/icon-only.svg などから各サイズを生成
```

Web（ホーム画面に追加）向けの `public/icons/*.png` は同じ SVG から
`sharp-cli` で作ってある。差し替えたら両方を作り直すこと。

## 6. TestFlight / App Store へ出す

配布と審査の手順は [docs/ios-release.md](ios-release.md) に分けてある（どこまで自動化できるか、人がやるしかない初回設定、提出前チェック）。

## 7. Mac が無い場合

GitHub Actions の `macos-14` ランナーでビルド・署名・TestFlight 提出まで
自動化できる（fastlane match / App Store Connect API キーを使う）。
初回の証明書まわりの設定は手間なので、まず Mac を借りて手で1回通してから
自動化するほうが早い。

## 8. 提出前に必要なもの（審査で落ちるもの）

- **アカウント削除**（App Store Review Guideline 5.1.1(v)）: アカウントを作れる
  アプリは、**アプリ内から**アカウント削除を開始できないと審査で落ちる。
  現状このアプリに削除機能は無く、バックエンドにも削除エンドポイントが無い
  （`backend/accounts/urls.py`）。**未対応の宿題**。
- **プライバシーポリシーの URL**: App Store Connect で必須。収集している
  項目（メールアドレス・大学名・学生証画像・解答履歴）を書く。
- **Sign in with Apple**: Google など第三者のログインを追加した時点で
  必須になる。現状はメール＋パスワードとマジックリンクだけなので不要。
- **年齢制限とカテゴリ**: 医学教育アプリとして「メディカル」か「教育」。
  医療行為の助言ではないことを説明文に書いておく。
- **学生証アップロード**を有効にする場合、`Info.plist` の
  `NSCameraUsageDescription` / `NSPhotoLibraryUsageDescription` の文面が
  実際の用途と合っているか確認する（設定済み）。

## 9. よくある落とし穴

| 症状 | 原因 |
|---|---|
| 全部の通信が「APIに接続できませんでした」 | `VITE_API_BASE_URL` 未設定のままビルドした |
| メールのリンクを踏んでもアプリに戻らない | Supabase の Redirect URLs にスキームを入れていない |
| ログインし直しを毎回求められる | `@capacitor/preferences` に保存できていない（`src/native.js`） |
| 画面の上がステータスバーに隠れる | `env(safe-area-inset-*)` を使っていない CSS を足した |
| 入力欄をタップすると勝手に拡大する | その入力欄の `font-size` が 16px 未満 |
| 外部リンクを踏むと戻れなくなる | `nativeBootstrap.js` の in-app ブラウザ処理を通っていない |
