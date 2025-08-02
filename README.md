# HiyoLab Bot

濱岸ひよりのファンクラブページ（ https://hamagishihiyori.fanpla.jp/ ）を定期的に監視し、更新があればDiscordチャンネルとX(Twitter)に通知するBotです。

## 概要

- FCページの主要セクション（INFORMATION, BLOG, MOVIE, PHOTO, Q&A）を対象に監視
- メンバー限定ページ（トーク）の新着メッセージも監視
- 各セクション内のaタグ（リンク）のhrefリストを比較し、新しいリンクが追加された場合のみ差分として検出
- 変更があった場合、Discordの指定チャンネルにメッセージを投稿
- 変更があった場合、X(Twitter)にメッセージを投稿（タイムスタンプ付きURLで重複投稿を回避）

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
│       └── talk_watcher.py      # トーク（コメント）監視
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

---

## ライセンス

このプロジェクトはMITライセンスの下でライセンスされています。詳細は`LICENSE`ファイルを参照してください。
