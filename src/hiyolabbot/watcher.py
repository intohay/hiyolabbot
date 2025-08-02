import json
import logging
import pathlib
import re

import bs4  # beautifulsoup4
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------- site‑specific settings -----------------------------------------
URL = "https://hamagishihiyori.fanpla.jp/"

TRACK_SELECTORS = {
    # CSS selector : human‑readable label    （必要に応じて編集）
    "section#news": "INFORMATION",
    "section#blog": "BLOG",
    "section#movie": "MOVIE",
    "section#photo": "PHOTO",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
TIMEOUT = 30  # seconds

SNAPSHOT_FILE = pathlib.Path("snapshot.json")
# ---------------------------------------------------------------------------


def fetch_html() -> bs4.BeautifulSoup:
    """Download the page and return parsed soup."""
    logging.info("Fetching HTML from URL")
    resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return bs4.BeautifulSoup(resp.text, "lxml")


def extract_item_ids(section: bs4.Tag | None) -> list[str]:
    """Extract identifier list for items in a section.

    今回は各コンテンツへのリンク (href) を ID 代わりに使用する。
    リンクのテキストや日付が微修正されても href が変わらない限り
    差分として検知しないため、"新しいコンテンツ追加" の検知に強い。
    
    末尾が5桁以上の数字で終わるURL（detail系）のみを抽出する。
    """
    if section is None:
        return []

    hrefs: list[str] = []
    for a in section.find_all("a", href=True):
        href: str = a["href"].strip()
        # 不要なクエリパラメータや末尾のスラッシュを除去して正規化
        href = href.split("?")[0].rstrip("/")
        
        # 末尾が5桁以上の数字で終わるURLのみを追加（detail系のURL）
        if re.search(r'/\d{5,}$', href):
            hrefs.append(href)

    # 重複除去（順序維持）
    seen: set[str] = set()
    unique_hrefs = [h for h in hrefs if not (h in seen or seen.add(h))]
    return unique_hrefs


def make_snapshot(soup: bs4.BeautifulSoup) -> dict[str, list[str]]:
    """Create current snapshot mapping label -> list of item identifiers."""
    snap: dict[str, list[str]] = {}
    for selector, label in TRACK_SELECTORS.items():
        section = soup.select_one(selector)
        snap[label] = extract_item_ids(section)
    return snap


def load_previous() -> dict[str, list[str]] | None:
    if SNAPSHOT_FILE.exists():
        return json.loads(SNAPSHOT_FILE.read_text(encoding="utf‑8"))
    return None


def save_snapshot(snap: dict[str, list[str]]) -> None:
    logging.info("Saving snapshot")
    SNAPSHOT_FILE.write_text(json.dumps(snap, ensure_ascii=False, indent=2))


def diff(prev: dict[str, list[str]] | None, curr: dict[str, list[str]]) -> list[str]:
    """Return list of labels where *new* items appeared since last snapshot."""
    logging.info("Calculating differences")

    # 以前の形式（ハッシュ文字列）で保存されている場合は、初回とみなす
    if prev is None or any(not isinstance(v, list) for v in prev.values()):
        return ["初回スキャン（スナップショット作成）"]

    changes: list[str] = []
    for label, curr_ids in curr.items():
        prev_ids = prev.get(label, [])
        # 以前存在しなかった ID があるか？
        new_items = set(curr_ids) - set(prev_ids)
        if new_items:
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
