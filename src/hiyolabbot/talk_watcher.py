import json
import logging
import os
import pathlib
import re
import tempfile
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------- site-specific settings -----------------------------------------
TALK_URL = "https://hamagishihiyori.fanpla.jp/community/detail/55/?f=artist"
LOGIN_URL = "https://hamagishihiyori.fanpla.jp/1/login/"

TALK_SNAPSHOT_FILE = pathlib.Path("talk_snapshot.json")
SESSION_FILE = pathlib.Path("playwright_session.json")
# ---------------------------------------------------------------------------


async def login_and_save_session(browser: Browser, plusmember_id: str, password: str) -> Page:
    """ログインしてセッションを保存する"""
    logging.info("Starting login process for talk monitoring")
    
    context = await browser.new_context()
    page = await context.new_page()
    
    # ログインページへ移動
    await page.goto(LOGIN_URL)
    await page.wait_for_load_state("networkidle")
    
    # ログインフォームに入力
    await page.fill('input[name="form[id]"]', plusmember_id)
    await page.fill('input[name="form[pass]"]', password)
    
    # ログインボタンをクリック
    await page.click('input[type="submit"]')
    
    # ログイン後のページ遷移を待つ
    await page.wait_for_load_state("networkidle")
    
    # セッション情報を保存
    storage_state = await context.storage_state()
    SESSION_FILE.write_text(json.dumps(storage_state, ensure_ascii=False, indent=2))
    logging.info("Session saved successfully")
    
    return page


async def fetch_talk_page(plusmember_id: str, password: str) -> tuple[Page, Browser]:
    """トークページを取得してPageオブジェクトを返す"""
    browser = await async_playwright().start().chromium.launch(headless=True)
    
    try:
        # セッションファイルが存在する場合は再利用を試みる
        if SESSION_FILE.exists():
            logging.info("Using existing session for talk page")
            context = await browser.new_context(storage_state=SESSION_FILE)
            page = await context.new_page()
            await page.goto(TALK_URL)
            await page.wait_for_load_state("networkidle")
            
            # ログイン状態を確認（ログインページにリダイレクトされていないか）
            if page.url.startswith(LOGIN_URL):
                logging.info("Session expired, logging in again")
                await context.close()
                page = await login_and_save_session(browser, plusmember_id, password)
                await page.goto(TALK_URL)
                await page.wait_for_load_state("networkidle")
        else:
            logging.info("No existing session, logging in")
            page = await login_and_save_session(browser, plusmember_id, password)
            await page.goto(TALK_URL)
            await page.wait_for_load_state("networkidle")
        
        # チャットエリアが読み込まれるまで待つ
        await page.wait_for_selector('#chat-area', timeout=10000)
        
        return page, browser
        
    except Exception as e:
        await browser.close()
        raise e


async def extract_comment_ids(plusmember_id: str, password: str) -> list[str]:
    """トークページからコメントIDを抽出"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        try:
            # セッションファイルが存在する場合は再利用を試みる
            if SESSION_FILE.exists():
                logging.info("Using existing session for talk page")
                context = await browser.new_context(storage_state=SESSION_FILE)
                page = await context.new_page()
                await page.goto(TALK_URL)
                await page.wait_for_load_state("networkidle")
                
                # ログイン状態を確認（ログインページにリダイレクトされていないか）
                if page.url.startswith(LOGIN_URL):
                    logging.info("Session expired, logging in again")
                    await context.close()
                    page = await login_and_save_session(browser, plusmember_id, password)
                    await page.goto(TALK_URL)
                    await page.wait_for_load_state("networkidle")
            else:
                logging.info("No existing session, logging in")
                page = await login_and_save_session(browser, plusmember_id, password)
                await page.goto(TALK_URL)
                await page.wait_for_load_state("networkidle")
            
            # チャットエリアが読み込まれるまで待つ
            await page.wait_for_selector('#chat-area', timeout=10000)
            
            # comment-body-* のIDを持つp要素を全て取得
            comment_elements = await page.query_selector_all('#chat-area ul li div p[id^="comment-body-"]')
            
            comment_ids = []
            for element in comment_elements:
                element_id = await element.get_attribute('id')
                if element_id:
                    # comment-body-12345 から 12345 を抽出
                    match = re.match(r'comment-body-(\d+)', element_id)
                    if match:
                        comment_ids.append(match.group(1))
            
            logging.info(f"Found {len(comment_ids)} comments")
            return comment_ids
            
        finally:
            await browser.close()


def make_talk_snapshot(comment_ids: list[str]) -> dict[str, list[str]]:
    """トークのスナップショットを作成"""
    return {
        "talk_comments": sorted(comment_ids, key=int)  # 数値順にソート
    }


def load_talk_previous() -> Optional[dict[str, list[str]]]:
    """以前のトークスナップショットを読み込む"""
    if TALK_SNAPSHOT_FILE.exists():
        return json.loads(TALK_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    return None


def save_talk_snapshot(snap: dict[str, list[str]]) -> None:
    """トークスナップショットを保存"""
    logging.info("Saving talk snapshot")
    data = json.dumps(snap, ensure_ascii=False, indent=2)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=TALK_SNAPSHOT_FILE.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(data)
        pathlib.Path(tmp_path).replace(TALK_SNAPSHOT_FILE)
    except BaseException:
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise


def diff_talk(prev: Optional[dict[str, list[str]]], curr: dict[str, list[str]]) -> list[str]:
    """トークの差分を検出"""
    logging.info("Calculating talk differences")
    
    if prev is None:
        return ["トーク初回スキャン（スナップショット作成）"]
    
    prev_ids = set(prev.get("talk_comments", []))
    curr_ids = set(curr.get("talk_comments", []))
    
    new_comment_ids = curr_ids - prev_ids
    
    if new_comment_ids:
        new_count = len(new_comment_ids)
        return [f"新しいトーク: {new_count}件のメッセージ"]
    
    return []


async def check_talk_updates(plusmember_id: str, password: str) -> list[str]:
    """トークページの更新をチェックして変更があった場合の説明を返す"""
    try:
        comment_ids = await extract_comment_ids(plusmember_id, password)
        curr = make_talk_snapshot(comment_ids)
        prev = load_talk_previous()
        changes = diff_talk(prev, curr)
        save_talk_snapshot(curr)
        return changes
    except Exception as e:
        logging.error(f"Failed to check talk updates: {e}")
        raise
    
if __name__ == "__main__":
    import asyncio
    import os
    
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(check_talk_updates(os.environ["PLUSMEMBER_ID"], os.environ["PLUSMEMBER_PASSWORD"]))