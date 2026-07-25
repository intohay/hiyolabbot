# HiyoLab Bot

濱岸ひよりのファンクラブページ（ https://hamagishihiyori.fanpla.jp/ ）を定期的に監視し、更新があればDiscordチャンネルとX(Twitter)、LINEに通知するBotです。

## 概要

- FCページの主要セクション（INFORMATION, BLOG, MOVIE, PHOTO, Q&A）を対象に監視
- メンバー限定ページ（トーク）の新着メッセージも監視
- 各セクション内のaタグ（リンク）のhrefリストを比較し、新しいリンクが追加された場合のみ差分として検出
- 変更があった場合、Discordの指定チャンネルにメッセージを投稿
- 変更があった場合、X(Twitter)にメッセージを投稿（タイムスタンプ付きURLで重複投稿を回避）
- 変更があった場合、LINE Bot によるメッセージを投稿

## 前提条件

- Python 3.12 以上
- [`uv`](https://github.com/astral-sh/uv) がインストールされていること（依存解決に使用）
- Chromium（メンバー限定ページ監視に必要）

## セットアップ

### 1. `uv` のインストール（未インストールの場合）

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
````

または pip で：

```bash
pip install uv
```

### 2. 依存パッケージのインストール

```bash
uv pip install --requirements pyproject.toml
```

このコマンドはカレントディレクトリの `pyproject.toml` を読み取り、必要な依存を自動で解決・インストールします。

### 3. Playwright ブラウザのインストール

メンバー限定ページの監視にはChromiumが必要です：

```bash
# Ubuntu/Debian の場合、まずシステム依存関係をインストール
sudo playwright install-deps chromium

# その後、Chromiumブラウザをインストール
playwright install chromium
```

### 4. 環境変数の設定

実行前に環境変数を設定してください：

```bash
cp .env.example .env
```

その後、`.env` ファイルに以下の値を入力してください：

- **Discord関連**
  - `DISCORD_TOKEN`: Discord Botのトークン
  - `DISCORD_CHANNEL_ID`: 通知を送信するチャンネルID
  - `DEV_CHANNEL_ID`: エラーメッセージを送信する開発用チャンネルID

- **Twitter/X関連**
  - `CONSUMER_KEY`: Twitter API のConsumer Key
  - `CONSUMER_SECRET`: Twitter API のConsumer Secret
  - `ACCESS_TOKEN`: Twitter API のAccess Token
  - `ACCESS_TOKEN_SECRET`: Twitter API のAccess Token Secret
  - `BEARER_TOKEN`: Twitter API のBearer Token

- **メンバー限定ページ関連（オプション）**
  - `PLUSMEMBER_ID`: ファンクラブのログインID
  - `PLUSMEMBER_PASSWORD`: ファンクラブのパスワード

- **LINE Bot関連**
  - `LINE_ACCESS_TOKEN`: LINE Bot に紐づくアクセストークン

- **死活監視関連（オプション）**
  - `HEALTHCHECK_URL`: [Healthchecks.io](https://healthchecks.io) の Ping URL。設定すると監視ループが1周正常に完了するたびにハートビートを送信する。未設定の場合は何も送信しない。

- **HiyoLove アプリ連携関連（オプション）**
  - `HIYOLOVE_SA_KEY`: Firestore 書き込み用サービスアカウント鍵（JSON）のファイルパス。**未設定なら Firestore への書き出しは丸ごと無効**になり、他の通知（Discord / X / LINE）には一切影響しない。設定する場合は後述の「HiyoLove アプリ連携について」を参照。

### 5. Bot の起動

```bash
python src/hiyolabbot/main.py
```

---

## ディレクトリ構成

```
.
├── src
│   └── hiyolabbot
│       ├── __init__.py          # パッケージ初期化ファイル
│       ├── main.py              # メインBot（エントリポイント）
│       ├── watcher.py           # 公開ページのスナップショット取得・差分検出ロジック
│       ├── member_watcher.py    # メンバー限定ページ監視（Playwright使用）
│       ├── talk_watcher.py      # トーク（コメント）監視
│       └── firestore_notifier.py # HiyoLove アプリ向け Firestore 書き出し（オプション）
├── tests/                       # テストコード
├── .github/workflows/deploy.yml # GitHub Actions による自動デプロイ設定
├── pyproject.toml               # 依存パッケージ管理ファイル
├── CLAUDE.md                    # Claude Code用の開発ガイドライン
└── .env.example                 # 環境変数のテンプレート
```

---

## テスト

```bash
PYTHONPATH=src python -m unittest discover tests
```

## デプロイ

GitHub Actions を使用した自動デプロイが設定されています：

1. `main` ブランチへのプッシュで自動的にデプロイが開始
2. テストが成功した場合のみ、Sakuraサーバーへデプロイ
3. systemd サービスとして稼働

## 補足

* BotがDiscordチャンネルにメッセージを投稿するためには、対象のサーバーに正しく参加しており、メッセージ送信権限がある必要があります。
* `TRACK_SELECTORS` は CSS セレクタで指定されているので、FCページ側のDOM構造が変更された場合には更新が必要になる可能性があります。
* 差分検出は「各セクション内のaタグのhref属性（リンク先URL）」をIDとして扱い、**新しいリンクが追加された場合のみ通知**します。リンクテキストや日付の微修正では通知されません。
* メンバー限定ページの監視にはPlaywrightによるブラウザ自動化を使用しており、セッション情報は `playwright_session.json` に保存されます。
* エラーが発生した場合は、`DEV_CHANNEL_ID` で指定された開発用チャンネルに通知されます。
* `HEALTHCHECK_URL` を設定すると、監視ループが1周正常に完了するたびに [Healthchecks.io](https://healthchecks.io) へハートビート（Ping）を送信します。プロセスの停止・サーバーダウン・ネットワーク断などで Ping が途絶えると Healthchecks.io 側から通知されるため、Discord のエラー通知（アプリ稼働が前提）ではカバーできない「アプリごと落ちたケース」の外部監視ができます。

---

## HiyoLove アプリ連携について（オプション機能・要外部設定）

更新検知を Firestore の `updates` コレクションにも書き出し、連携する iOS アプリ「HiyoLove」（個人用・非公式）へプッシュ通知を飛ばせます。**この機能は bot 単体では完結せず、以下の外部設定が前提**です。設定しない場合（`HIYOLOVE_SA_KEY` 未設定）は機能全体が無効になるだけで、既存の通知には影響しません。

**前提となる外部リソース（bot リポジトリの外にあるもの）:**

* Firebase プロジェクト（Firestore + Cloud Functions）。Cloud Functions が `updates` への `onDocumentCreated` で発火し、アプリへプッシュ通知を送る
* Firestore へ**書き込みのみ**可能なサービスアカウント。読み取り権限は意図的に付与しない（端末のプッシュトークンが読めると第三者が全端末へ通知を送れてしまうため）。したがって bot は Firestore を読んで既読判定することはできず、既読管理は従来どおり `snapshot.json` / `talk_snapshot.json` で行う
* サービスアカウントの鍵（JSON）はリポジトリ外に置き `chmod 600` とし、パスを `HIYOLOVE_SA_KEY` で渡す（git には絶対に入れない）

**書き込み内容の方針（アプリ側の設計と対）:**

* 公開4セクション（INFORMATION / BLOG / MOVIE / PHOTO）: タイトル・記事の絶対URL・サイト表示上の日付のみ。本文・画像・動画は書かない
* ひよりとーく（TALK）: **閲覧自体が会員限定のため、タイトルすら書かない**。検知イベント（section と検知時刻）のみ
* ドキュメントIDは URL / コメントIDから決定的に生成（例: `news-85341`、`talk-111829`）。`onDocumentCreated` は同一IDの再書き込みでは発火しないため、これが重複通知の防止になっている
* 過去記事をまとめて投入する場合のみ `notify=false` を付ける（アプリ側で通知を抑制）

---

## ライセンス

このプロジェクトはMITライセンスの下でライセンスされています。詳細は`LICENSE`ファイルを参照してください。
