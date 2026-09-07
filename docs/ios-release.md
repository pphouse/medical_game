# iOS リリース手順（Mac 側セッション向け）

`docs/ios.md` がアプリの作り方、こちらが**配布と審査**の手順。
Mac 上の Claude セッション（デスクトップアプリ / Claude Code CLI）が
そのまま引き継げるように書いてある。

## どこまで自動化できるか

App Store Connect API キー（`.p8`）を1本用意すると、**Apple ID の
2要素認証を通らずに**大半が CLI から回せる。逆に言うと、キーを作るまでは
どうしても Web の操作が要る。

| やること | 自動化 |
|---|---|
| ビルド・署名 | ○ `xcodebuild -allowProvisioningUpdates` / fastlane |
| TestFlight へアップロード | ○ `fastlane pilot upload` |
| スクリーンショット撮影 | ○ `fastlane snapshot`（シミュレータ） |
| 名前・説明・キーワード・What's New | ○ `fastlane deliver` |
| 年齢制限・App Privacy の申告 | ○ API にエンドポイントあり |
| 審査へ提出 | ○ `fastlane deliver --submit_for_review` |
| リジェクト後の修正・再提出 | ○（再ビルドして再提出するだけ） |
| **Developer Program の登録** | ✗ Apple の審査待ち |
| **API キー（.p8）の発行** | ✗ Web UI・Account Holder 権限 |
| **各種契約への同意**（無料アプリでも必要） | ✗ Web UI・Account Holder のみ |
| **アプリレコードの新規作成** | ✗ 公開 API に作成エンドポイントが無い。`fastlane produce` はできるが Apple ID ログイン＋2FA になるので、ポータルで1回作るほうが早い |
| **Resolution Center での返信**（リジェクト時） | ✗ 公開 API が無い |
| 説明文・年齢制限の回答・App Privacy の中身 | △ 下書きは自動。**事実の申告なので人が確認して出す** |
| Apple の審査そのもの | ✗ |

つまり **「最初に Web で15分ほど設定 → 以降は全自動」** が現実的な形。
Apple はこのあたりの仕様をときどき変えるので、詰まったら実際の
App Store Connect の画面を正とすること。

## 0. 人がやる初回セットアップ

- [ ] Apple Developer Program の登録完了（申込済み・Apple 待ち）
- [ ] App Store Connect → ユーザとアクセス → 統合 → App Store Connect API
      で **キーを作成**（役割は App Manager 以上）。
      `.p8` は**一度しかダウンロードできない**。Key ID と Issuer ID も控える。
      `.p8` はリポジトリに置かない（`~/.appstoreconnect/private_keys/` など）。
- [ ] 契約・税金・口座 → **無料アプリ用の契約に同意**（これが未同意だと
      提出しても弾かれる）
- [ ] App Store Connect でアプリを新規作成
      - プラットフォーム: iOS
      - 名前: 例「CBT国試クイズ」（App Store 上で一意。取られていたら変える）
      - 主要言語: 日本語
      - Bundle ID: `jp.pphouse.medquiz`（Certificates → Identifiers で先に登録）
      - SKU: 何でもよい（例 `medquiz-ios`）
- [ ] **プライバシーポリシーの URL** を用意して公開しておく（必須）

## 1. Mac 側セッションがやること

### 前提

```sh
xcode-select --install
sudo xcodebuild -license accept
brew install fastlane   # または gem install fastlane
```

### 接続先の設定

`frontend/.env.production` を作る（コミットされない）:

```sh
VITE_API_BASE_URL=https://<バックエンドのドメイン>/api
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>
```

`npm run build:ios` がこの3つを検証してからビルドする。

### ビルドと同期

```sh
cd frontend
npm ci
npm run ios:sync     # build:ios → cap sync ios
```

### 署名

ひとり開発なら **Xcode の自動署名 + API キー**が一番楽で、証明書用の
プライベートリポジトリ（fastlane match）は要らない。

```sh
xcodebuild -project ios/App/App.xcodeproj -scheme App \
  -destination 'generic/platform=iOS' \
  -allowProvisioningUpdates \
  -authenticationKeyPath "$ASC_KEY_PATH" \
  -authenticationKeyID "$ASC_KEY_ID" \
  -authenticationKeyIssuerID "$ASC_ISSUER_ID" \
  archive -archivePath build/App.xcarchive
```

初回は Xcode を開いて Signing & Capabilities で Team を選ぶのが確実
（`npm run ios:open`）。複数人で証明書を共有する段階になったら
`fastlane match` に移す。

### TestFlight へ

```sh
fastlane pilot upload --ipa build/App.ipa
```

`fastlane` の `app_store_connect_api_key` アクションに Key ID / Issuer ID /
`.p8` のパスを渡すと 2FA を通らずに済む。

### メタデータと提出

`fastlane deliver init` でひな形を作り、`fastlane/metadata/ja/` を埋めて

```sh
fastlane deliver --submit_for_review
```

## 2. 提出前チェック

- [ ] **アカウント削除がアプリ内から開始できる**（Guideline 5.1.1(v)）
      — **未実装**。これが無いと確実に落ちる
- [ ] プライバシーポリシーの URL を App Store Connect に設定
- [ ] App Privacy（収集データの申告）: メールアドレス・大学名・学生証画像・
      解答履歴。実装と食い違うと後で差し戻される
- [ ] 説明文に**医療行為の助言ではない**旨を書く（医学教育アプリとして）
- [ ] カテゴリは「メディカル」または「教育」
- [ ] デモ用アカウント（審査担当者がログインできるもの）を審査メモに書く。
      メール確認が要るログインだと審査で止まりやすい
- [ ] 実機で一通り触る: ログイン → 演習 → 解説表示 → 復習 → 対戦
- [ ] メールのリンク（マジックリンク）でアプリに戻れること。
      Supabase の Redirect URLs に `jp.pphouse.medquiz://auth-callback` が
      入っているか（`docs/ios.md` 参照）

App Store 用アイコンにアルファチャンネルが無いこと（提出時の定番の弾かれ方）は
確認済み。`@capacitor/assets` が不透明な RGB で書き出している。

## 3. リジェクトされたら

Resolution Center の返信だけは Web でやる。コードの修正が要るものは、
指摘内容を Mac 側セッションに渡せばそのまま直して再提出できる。

よくある指摘:

| 指摘 | 対応 |
|---|---|
| 5.1.1(v) アカウント削除が無い | アプリ内に削除導線を足す（上記） |
| 5.1.1 不要な情報の要求 | 学生証アップロードを必須にしない |
| 2.1 デモアカウントで確認できない | 審査メモに動くアカウントを書く |
| 4.2 機能が最小限 | 実質は問題演習アプリなので通常は問題にならない |
| 1.4.1 医療に関する断定 | 説明文と免責の書き方を直す |
