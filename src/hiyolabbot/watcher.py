import datetime
import json
import logging
import os
import pathlib
import re
import tempfile

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

# サイト表示上の日付（YYYY.MM.DD）は日本時間として解釈する
JST = datetime.timezone(datetime.timedelta(hours=9))
# ---------------------------------------------------------------------------


def fetch_html() -> bs4.BeautifulSoup:
    """Download the page and return parsed soup."""
    logging.info("Fetching HTML from URL")
    resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return bs4.BeautifulSoup(resp.text, "lxml")


def _normalize_href(href: str) -> str | None:
    """href を正規化し、detail 系（末尾が5桁以上の数字）でなければ None を返す。

    extract_item_ids と extract_item_details で同じ正規化を使うことで、
    差分結果（href）と詳細（タイトル・日付）をキーで突き合わせられる。
    """
    # 不要なクエリパラメータや末尾のスラッシュを除去して正規化
    href = href.strip().split("?")[0].rstrip("/")
    # 末尾が5桁以上の数字で終わるURLのみを対象（detail系のURL）
    if re.search(r'/\d{5,}$', href):
        return href
    return None


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
        href = _normalize_href(a["href"])
        if href is not None:
            hrefs.append(href)

    # 重複除去（順序維持）
    seen: set[str] = set()
    unique_hrefs = [h for h in hrefs if not (h in seen or seen.add(h))]
    return unique_hrefs


def extract_item_details(section: bs4.Tag | None) -> dict[str, dict]:
    """セクション内の各記事について href -> {"title", "posted_at"} を返す。

    href は extract_item_ids と同じ正規化を通した相対URL。
    タイトルは <a> 内の p.tit を優先する（<a> 全体のテキストは
    日付・カテゴリ・コメント数まで連結されてしまうため使えない）。
    p.tit が無ければ <a> のテキスト、それも無ければ空文字。
    日付は p.date の YYYY.MM.DD を JST の 0 時として解釈し、
    取れなければ None。
    """
    details: dict[str, dict] = {}
    if section is None:
        return details

    for a in section.find_all("a", href=True):
        href = _normalize_href(a["href"])
        if href is None or href in details:
            continue

        tit_tag = a.select_one("p.tit")
        if tit_tag is not None:
            title = tit_tag.get_text(strip=True)
        else:
            title = a.get_text(strip=True)

        posted_at: datetime.datetime | None = None
        date_tag = a.select_one("p.date")
        if date_tag is not None:
            m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_tag.get_text(strip=True))
            if m:
                try:
                    posted_at = datetime.datetime(
                        int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST
                    )
                except ValueError:
                    posted_at = None

        details[href] = {"title": title, "posted_at": posted_at}
    return details


def make_snapshot(soup: bs4.BeautifulSoup) -> dict[str, list[str]]:
    """Create current snapshot mapping label -> list of item identifiers."""
    snap: dict[str, list[str]] = {}
    for selector, label in TRACK_SELECTORS.items():
        section = soup.select_one(selector)
        snap[label] = extract_item_ids(section)
    return snap


def make_details(soup: bs4.BeautifulSoup) -> dict[str, dict[str, dict]]:
    """ラベル -> {href -> {"title", "posted_at"}} の詳細マップを作る。"""
    details: dict[str, dict[str, dict]] = {}
    for selector, label in TRACK_SELECTORS.items():
        section = soup.select_one(selector)
        details[label] = extract_item_details(section)
    return details


def load_previous() -> dict[str, list[str]] | None:
    if SNAPSHOT_FILE.exists():
        try:
            text = SNAPSHOT_FILE.read_text(encoding="utf-8")
            if not text.strip():
                logging.warning("snapshot.json is empty, treating as first scan")
                return None
            return json.loads(text)
        except json.JSONDecodeError:
            logging.warning("snapshot.json is corrupted, treating as first scan")
            return None
    return None


def save_snapshot(snap: dict[str, list[str]]) -> None:
    logging.info("Saving snapshot")
    data = json.dumps(snap, ensure_ascii=False, indent=2)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=SNAPSHOT_FILE.parent, suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(data)
        pathlib.Path(tmp_path).replace(SNAPSHOT_FILE)
    except BaseException:
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise


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


def diff_items(
    prev: dict[str, list[str]] | None, curr: dict[str, list[str]]
) -> dict[str, list[str]]:
    """ラベル -> 新着 href リストを返す（ページ上の表示順を維持）。

    diff() と違い新着そのもの（href）を返す。Firestore 書き出しなど、
    個別記事のURLが必要な用途向け。初回スキャン（prev が None または
    旧形式）では空 dict を返し、呼び出し側で何も起きないようにする。
    """
    if prev is None or any(not isinstance(v, list) for v in prev.values()):
        return {}

    new_items: dict[str, list[str]] = {}
    for label, curr_ids in curr.items():
        prev_set = set(prev.get(label, []))
        fresh = [h for h in curr_ids if h not in prev_set]
        if fresh:
            new_items[label] = fresh
    return new_items


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
