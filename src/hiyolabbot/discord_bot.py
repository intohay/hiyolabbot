import discord
import os
import asyncio
from datetime import datetime, timezone
from watcher import make_snapshot, load_previous, diff, save_snapshot, URL, fetch_html
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
client = discord.Client(intents=intents)


CHECK_INTERVAL = 60  # 1 分ごと

async def watch_loop() -> None:
    await client.wait_until_ready()
    channel_id = int(os.environ["CHANNEL_ID"])
    channel = client.get_channel(channel_id)
    if channel is None:
        raise RuntimeError(f"Channel {channel_id} not found or bot lacks access.")

    while not client.is_closed():
        curr = make_snapshot(fetch_html())
        prev = load_previous()
        changes = diff(prev, curr)
        if changes and changes != ["初回スキャン（スナップショット作成）"]:
            timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            change_descriptions = "\n".join(f"• {c}" for c in changes)
            msg = (
                "@everyone\n"
                f"[ひよラボ]({URL})が更新されました！\n"
                f"以下のセクションに変更がありました:\n{change_descriptions}"
            )
            await channel.send(msg)
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
