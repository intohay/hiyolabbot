from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import pathlib
from datetime import datetime, timezone

import bs4  # beautifulsoup4
import discord
import requests

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------- site‑specific settings -----------------------------------------
URL = "https://hamagishihiyori.fanpla.jp/"

TRACK_SELECTORS = {
    # CSS selector : human‑readable label    （必要に応じて編集）
    "section#news": "INFORMATION",
    "section#schedule": "SCHEDULE",
    "section#blog": "BLOG",
    "section#movie": "MOVIE",
    "section#photo": "PHOTO",
    "section#qa": "Q&A"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
TIMEOUT = 15  # seconds

SNAPSHOT_FILE = pathlib.Path("snapshot.json")
# ---------------------------------------------------------------------------


def fetch_html() -> bs4.BeautifulSoup:
    """Download the page and return parsed soup."""
    logging.info("Fetching HTML from URL")
    resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return bs4.BeautifulSoup(resp.text, "lxml")



def hash_text(node: bs4.Tag | None) -> str | None:
    """Return SHA‑256 of node's normalised text, or None if node missing."""
    if node is None:
        return None
    # テキストを取得し、数字を削除
    norm = " ".join(node.get_text(" ", strip=True).split())
    # 数字を削除
    norm = re.sub(r'\d+', '', norm)
    return hashlib.sha256(norm.encode()).hexdigest()


def make_snapshot(soup: bs4.BeautifulSoup) -> dict[str, str | None]:
    return {
        label: hash_text(soup.select_one(selector))
        for selector, label in TRACK_SELECTORS.items()
    }


def load_previous() -> dict[str, str | None] | None:
    if SNAPSHOT_FILE.exists():
        return json.loads(SNAPSHOT_FILE.read_text(encoding="utf‑8"))
    return None


def save_snapshot(snap: dict[str, str | None]) -> None:
    logging.info("Saving snapshot")
    SNAPSHOT_FILE.write_text(json.dumps(snap, ensure_ascii=False, indent=2))


def diff(prev: dict[str, str | None] | None, curr: dict[str, str | None]) -> list[str]:
    logging.info("Calculating differences")
    if prev is None:
        return ["初回スキャン（スナップショット作成）"]

    changes: list[str] = []
    for label, new_hash in curr.items():
        old_hash = prev.get(label)
        if old_hash != new_hash:
            # セクションの追加や削除は想定していないので、単純に更新として扱う
            changes.append(label)
    return changes



if __name__ == "__main__":
    logging.info("Starting watcher")
   
    logging.info("Fetching HTML")
    soup = fetch_html()
    logging.info("Making snapshot")
    snapshot = make_snapshot(soup)
    logging.info("Diffing")
    changes = diff(load_previous(), snapshot)
    logging.info("Saving snapshot")
    save_snapshot(snapshot)
    logging.info("Changes: %s", changes)
