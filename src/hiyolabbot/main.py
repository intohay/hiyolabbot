import discord
import os
import asyncio
from datetime import datetime
from watcher import make_snapshot, load_previous, diff, save_snapshot, URL, fetch_html
from dotenv import load_dotenv
from tweepy import Client
from urllib.parse import urljoin

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

async def watch_loop() -> None:
    await client.wait_until_ready()
    channel_id = int(os.environ["DISCORD_CHANNEL_ID"])
    channel = client.get_channel(channel_id)
    if channel is None:
        raise RuntimeError(f"Channel {channel_id} not found or bot lacks access.")

    while not client.is_closed():
        curr = make_snapshot(fetch_html())
        prev = load_previous()
        changes = diff(prev, curr)
        if changes and changes != ["初回スキャン（スナップショット作成）"]:
            change_descriptions = "\n".join(f"• {c}" for c in changes)
            msg = (
                "@everyone\n"
                f"[ひよラボ]({URL})が更新されました！\n"
                f"以下のセクションに変更がありました:\n{change_descriptions}"
            )
            await channel.send(msg)
            
            # https://hamagishihiyori.fanpla.jp/?t=202505030444 のように timestamp を含む URL を使用する
            # 理由: 
            #   こうすることで同じ内容のツイートではないと判定されて POST に失敗することがなくなる。
            #   また、t=xxx を含めても遷移先は https://hamagishihiyori.fanpla.jp/ にリダイレクトされる。
            #   その結果、ツイートのプレビューは https://hamagishihiyori.fanpla.jp/ のものになり、きれいに表示される。
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            x_link = urljoin(URL, f"?t={timestamp}")
            x_msg = f"ひよラボが更新されました！\n\n以下のセクションが更新されました:\n{change_descriptions}\n\n{x_link}"
            
            try:
                x_client.create_tweet(text=x_msg)
            except Exception as e:
                # 処理に失敗してもループを継続させる
                await channel.send(f"X に投稿に失敗しました: {e}\n投稿したかった文面:\n{x_msg}")
        
        save_snapshot(curr)
        await asyncio.sleep(CHECK_INTERVAL)


@client.event
async def on_ready() -> None:
    print(f"Logged in as {client.user} (id={client.user.id})")
    # Start background task once the gateway is ready:
    client.loop.create_task(watch_loop())


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set DISCORD_TOKEN environment variable.")
    client.run(token)
