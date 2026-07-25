import asyncio
import logging
import os
from datetime import datetime
from urllib.parse import urljoin

import discord
import requests
from dotenv import load_dotenv
from talk_watcher import check_talk_updates
from tweepy import Client
from watcher import URL, diff, fetch_html, load_previous, make_snapshot, save_snapshot

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    BroadcastRequest,
    TextMessage,
)
from linebot.v3.messaging.exceptions import ApiException as LineApiException

# glibc の A/AAAA 並列問い合わせは、長時間プロセスがアイドルなリゾルバソケットを
# 再利用する際に稀に EAI_NONAME を返す（実測: 素の状態 8/15 失敗 →
# single-request-reopen で 0/15）。A と AAAA を別ソケットで問い合わせることで解消する。
# 最初の名前解決より前に設定する必要があるため、ここで環境変数を立てておく。
os.environ.setdefault("RES_OPTIONS", "single-request-reopen")

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

# 公開ページ取得のリトライ設定（一過性の DNS / ネットワーク断への耐性）
FETCH_RETRY = 3          # 1 サイクル内での取得リトライ回数
FETCH_RETRY_WAIT = 5     # リトライ間隔（秒）
# 連続失敗がこの回数に達したときだけ DEV へ通知する（毎分の通知スパムを防ぐ）
FAILURE_NOTIFY_THRESHOLD = 5


def _broadcast_line_message(message: str) -> None:
    config = Configuration(access_token=os.environ.get("LINE_ACCESS_TOKEN"))

    try:
        with ApiClient(config) as api_client:
            messaging_api = MessagingApi(api_client)
            text_message = TextMessage(text=message)
            broadcast_request = BroadcastRequest(messages=[text_message])
            messaging_api.broadcast(broadcast_request)
    except LineApiException as e:
        # 無料枠の上限超過（429）は毎月恒常的に発生し、対応もしない方針のため
        # dev チャンネルへは通知せずログに残すだけにする。
        # それ以外（トークン失効など）は呼び出し側で dev チャンネルへ通知する。
        if e.status == 429:
            logging.info("LINE の月間上限（429）のため配信をスキップしました")
            return
        raise


def _ping_healthcheck() -> None:
    """Healthchecks.io へ死活監視のハートビートを送信する。

    HEALTHCHECK_URL が設定されている場合のみ ping を送る。
    監視 ping の失敗は本体の監視処理を止めないよう、例外は握りつぶす。
    一定時間 ping が途絶えると Healthchecks.io 側がダウンとして通知する。
    """
    url = os.environ.get("HEALTHCHECK_URL")
    if not url:
        return
    try:
        requests.get(url, timeout=10)
    except requests.exceptions.RequestException:
        pass


async def _fetch_html_with_retry() -> "object":
    """公開ページ取得を数回リトライする。

    一過性の DNS 解決失敗・ネットワーク断は数秒〜で回復することが多いため、
    1 サイクル内で FETCH_RETRY 回まで再試行する。全て失敗した場合は最後の
    例外を送出する（呼び出し側で連続失敗回数を管理して通知を制御する）。
    """
    last_exc: Exception | None = None
    for attempt in range(FETCH_RETRY):
        try:
            return fetch_html()
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < FETCH_RETRY - 1:
                await asyncio.sleep(FETCH_RETRY_WAIT)
    assert last_exc is not None
    raise last_exc


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

    # 公開ページ取得の連続失敗回数（一過性ブレの通知スパムを抑制するために使う）
    fetch_fail_streak = 0

    while not client.is_closed():
        # 公開ページの監視
        try:
            curr = make_snapshot(await _fetch_html_with_retry())
            prev = load_previous()
            changes = diff(prev, curr)
        except requests.exceptions.RequestException as e:
            fetch_fail_streak += 1
            # 一過性の失敗では通知せず、連続失敗が閾値に達したときだけ1回だけ通知する
            if fetch_fail_streak == FAILURE_NOTIFY_THRESHOLD:
                await dev_channel.send(
                    f"HTMLの取得に{FAILURE_NOTIFY_THRESHOLD}回連続で失敗しました"
                    f"（以降この連続失敗の通知は抑制します）: {e}"
                )
            await asyncio.sleep(CHECK_INTERVAL)
            continue
        except Exception as e:
            await dev_channel.send(f"公開ページの監視中にエラーが発生しました: {e}")
            await asyncio.sleep(CHECK_INTERVAL)
            continue
        else:
            # 取得に成功。直前まで閾値以上の連続失敗が続いていたら回復を通知する
            if fetch_fail_streak >= FAILURE_NOTIFY_THRESHOLD:
                await dev_channel.send("HTMLの取得が回復しました。")
            fetch_fail_streak = 0
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

            line_message = (
                "ひよラボが更新されました！\n"
                "以下のセクションに変更がありました:\n"
                f"{change_descriptions}\n"
                f"{URL}"
            )
            try:
                _broadcast_line_message(line_message)
            except Exception as e:
                await dev_channel.send(
                    f"LINE に投稿に失敗しました: {e}\n投稿したかった文面:\n{line_message}"
                )

        save_snapshot(curr)

        # トークページの監視（認証情報がある場合のみ）
        if plusmember_id and plusmember_password:
            try:
                talk_changes = await check_talk_updates(
                    plusmember_id, plusmember_password
                )
                if talk_changes and talk_changes != [
                    "トーク初回スキャン（スナップショット作成）"
                ]:
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

                    line_talk_message = (
                        "ひよりとーくが更新されました！\n"
                        "https://hamagishihiyori.fanpla.jp/community/detail/55/?f=artist"
                    )
                    try:
                        _broadcast_line_message(line_talk_message)
                    except Exception as e:
                        await dev_channel.send(
                            f"LINE にトーク更新の投稿に失敗しました: {e}\n投稿したかった文面:\n{line_talk_message}"
                        )

            except Exception as e:
                await dev_channel.send(
                    f"トークページの監視中にエラーが発生しました: {e}"
                )

        # 1周分の監視が正常に完了したのでハートビートを送信する
        _ping_healthcheck()

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
