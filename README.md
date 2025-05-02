# HiyoLab Bot

濱岸ひよりのファンクラブページ（ https://hamagishihiyori.fanpla.jp/ ）を定期的に監視し、更新があればDiscordチャンネルに通知するBotです。

## 概要

- FCページの主要セクション（INFORMATION, SCHEDULE, BLOG, MOVIE, PHOTO, Q&A）を対象に監視
- セクションごとのHTMLテキストのハッシュを比較し、差分を検出
- 変更があった場合、Discordの指定チャンネルにメッセージを投稿
- Python標準の非同期IO + `discord.py` による非同期Bot実装

## 前提条件

- Python 3.10 以上
- [`uv`](https://github.com/astral-sh/uv) がインストールされていること（依存解決に使用）

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

### 3. 環境変数の設定

実行前に環境変数を設定してください：

```bash
cp .env.example .env
```

その後、`.env` ファイルに値を入力してください。

### 4. Bot の起動

```bash
python main.py
```

---

## ディレクトリ構成

```
.
├── src
│   └── hiyolabbot
│       ├── __init__.py          # パッケージ初期化ファイル
│       ├── main.py       # メインBot（エントリポイント）
│       └── watcher.py           # スナップショット取得・差分検出ロジック
└── pyproject.toml               # 依存パッケージ管理ファイル
```

---

## 補足

* Botがチャンネルにメッセージを投稿するためには、対象のサーバーに正しく参加しており、メッセージ送信権限がある必要があります。
* `TRACK_SELECTORS` は CSS セレクタで指定されているので、FCページ側のDOM構造が変更された場合には更新が必要になる可能性があります。

---

## ライセンス

このプロジェクトはMITライセンスの下でライセンスされています。詳細は`LICENSE`ファイルを参照してください。
