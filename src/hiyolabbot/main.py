import asyncio
import os
from datetime import datetime
from urllib.parse import urljoin

import discord
import requests
from dotenv import load_dotenv
from tweepy import Client
from watcher import URL, diff, fetch_html, load_previous, make_snapshot, save_snapshot
from talk_watcher import check_talk_updates

load_dotenv()

intents = discord.Intents.default()
client = discord.Client(intents=intents)

x_client = Client(
    bearer_token=os.environ.get("X_BEARER_TOKEN"),
    consumer_key=os.environ.get("X_API_KEY"),
    consumer_secret=os.environ.get("X_API_KEY_SECRET"),
    access_token=os.environ.get("X_ACCESS_TOKEN"),
    access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET"),
)

CHECK_INTERVAL = 60  # 1 分ごと


# Ensure the background task starts only once
_watch_task: asyncio.Task | None = None

async def watch_loop() -> None:
    await client.wait_until_ready()
    channel_id = int(os.environ["CHANNEL_ID"])
    channel = client.get_channel(channel_id)
    if channel is None:
        raise RuntimeError(f"Channel {channel_id} not found or bot lacks access.")

    # 開発用チャンネルの取得
    dev_channel_id = int(os.environ["DEV_CHANNEL_ID"])
    dev_channel = client.get_channel(dev_channel_id)
    if dev_channel is None:
        raise RuntimeError(
            f"Dev channel {dev_channel_id} not found or bot lacks access."
        )

    # 会員ログイン情報の取得
    plusmember_id = os.environ.get("PLUSMEMBER_ID")
    plusmember_password = os.environ.get("PLUSMEMBER_PASSWORD")
    
    while not client.is_closed():
        # 公開ページの監視
        try:
            curr = make_snapshot(fetch_html())
        except requests.exceptions.RequestException as e:
            await dev_channel.send(f"HTMLの取得に失敗しました: {e}")
            continue  # ループを継続
        prev = load_previous()
        changes = diff(prev, curr)
        if changes and changes != ["初回スキャン（スナップショット作成）"]:
            change_descriptions = "\n".join(f"• {c}" for c in changes)
            msg = (
                "@everyone\n"
                f"ひよラボが更新されました！\n"
                f"以下のセクションに変更がありました:\n{change_descriptions}\n"
                f"{URL}\n"
            )
            await channel.send(msg)

            # https://hamagishihiyori.fanpla.jp/?t=202505030444 のように timestamp を含む URL を使用する
            # 理由:
            #   こうすることで同じ内容のツイートではないと判定されて POST に失敗することがなくなる。
            #   また、t=xxx を含めても遷移先は https://hamagishihiyori.fanpla.jp/ にリダイレクトされる。
            #   その結果、ツイートのプレビューは https://hamagishihiyori.fanpla.jp/ のものになり、きれいに表示される。
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            x_link = urljoin(URL, f"?t={timestamp}")
            x_msg = (
                "／\n"
                "📢 ひよラボが更新されました！\n"
                "＼\n"
                "以下のセクションが更新されました:\n"
                f"{change_descriptions}\n\n"
                "#HiyoLab\n"
                "#ひよラボ\n"
                "#濱岸ひより\n"
                f"{x_link}"
            )
            try:
                x_client.create_tweet(text=x_msg)
            except Exception as e:
                # 処理に失敗してもループを継続させる
                await dev_channel.send(
                    f"X に投稿に失敗しました: {e}\n投稿したかった文面:\n{x_msg}"
                )

        save_snapshot(curr)
        
        # トークページの監視（認証情報がある場合のみ）
        if plusmember_id and plusmember_password:
            try:
                talk_changes = await check_talk_updates(plusmember_id, plusmember_password)
                if talk_changes and talk_changes != ["トーク初回スキャン（スナップショット作成）"]:
                    
                    talk_msg = (
                        "@everyone\n"
                        "ひよりとーくが更新されました！\n"
                        "https://hamagishihiyori.fanpla.jp/community/detail/55/?f=artist\n"
                    )
                    await channel.send(talk_msg)
                    
                    # Twitterにも投稿
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    x_talk_link = f"https://hamagishihiyori.fanpla.jp/community/detail/55/?f=artist&t={timestamp}"
                    x_talk_msg = (
                        "／\n"
                        "💬 ひよりとーくが更新されました！\n"
                        "＼\n\n"
                        "#ひよりとーく\n"
                        "#ひよラボ\n"
                        "#HiyoLab\n"
                        "#濱岸ひより\n"
                        f"{x_talk_link}"
                    )
                    try:
                        x_client.create_tweet(text=x_talk_msg)
                    except Exception as e:
                        await dev_channel.send(
                            f"X にトーク更新の投稿に失敗しました: {e}\n投稿したかった文面:\n{x_talk_msg}"
                        )
            except Exception as e:
                await dev_channel.send(f"トークページの監視中にエラーが発生しました: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)


@client.event
async def on_ready() -> None:
    print(f"Logged in as {client.user} (id={client.user.id})")
    # Start background task once the gateway is ready:
    global _watch_task
    if _watch_task is None or _watch_task.done():
        _watch_task = client.loop.create_task(watch_loop())
        print("watch_loop started")
    else:
        print("watch_loop already running; skip starting a new one")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set DISCORD_TOKEN environment variable.")
    client.run(token)
