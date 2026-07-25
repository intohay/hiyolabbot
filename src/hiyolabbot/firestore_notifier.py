"""HiyoLove iOS アプリ向けの Firestore 書き出しモジュール。

Firestore の updates コレクションに1件書くと、アプリ側の Cloud Functions
(onDocumentCreated) が発火して端末にプッシュ通知が飛ぶ。

- HIYOLOVE_SA_KEY（サービスアカウント鍵ファイルのパス）が未設定なら
  書き出しは丸ごと無効（is_enabled() が False を返す）
- サービスアカウントは書き込み専用で Firestore を読めないため、
  既読判定は snapshot.json 側の仕組みに委ねる
- ドキュメントIDを URL から決定的に生成するため、同じ記事を2回書いても
  onDocumentCreated は初回しか発火しない（これが重複通知の防止策）
- 保存するのはタイトル・URL・日付のみ。本文・画像・動画、および
  会員限定コンテンツは保存しない（アプリの設計方針）
"""

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

_client = None


def is_enabled() -> bool:
    """HIYOLOVE_SA_KEY が設定されていれば有効。"""
    return bool(os.environ.get("HIYOLOVE_SA_KEY"))


def _get_client():
    # google-cloud-firestore は遅延 import（無効な環境では不要なため）
    global _client
    if _client is None:
        from google.cloud import firestore

        _client = firestore.Client.from_service_account_json(
            os.environ["HIYOLOVE_SA_KEY"]
        )
    return _client


def doc_id_for(url: str) -> str:
    """URL から Firestore ドキュメントIDを生成する。

    https://.../news/detail/85341      -> news-85341
    https://.../blog/detail/94931/     -> blog-94931
    https://.../photo/331/detail/79175 -> photo-79175
    パターン外は URL の SHA-1 先頭12文字にフォールバック。
    """
    path = urlparse(url).path.rstrip("/")
    m = re.match(r"^/([^/]+)(?:/[^/]+)*/detail/(\d+)$", path)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def build_updates(
    new_items: dict[str, list[str]],
    details_by_label: dict[str, dict[str, dict]],
    base_url: str,
) -> list[dict]:
    """diff_items() と make_details() の結果から書き込み用レコードを組み立てる。

    URL は base_url で絶対化する（アプリがそのまま開くため）。
    タイトルが取れなかった記事は空文字のまま書く（通知自体は出る）。
    """
    updates: list[dict] = []
    for label, hrefs in new_items.items():
        details = details_by_label.get(label, {})
        for href in hrefs:
            d = details.get(href, {})
            updates.append(
                {
                    "section": label,
                    "title": d.get("title", ""),
                    "url": urljoin(base_url, href),
                    "posted_at": d.get("posted_at"),
                }
            )
    return updates


def publish_updates(updates: list[dict]) -> int:
    """updates コレクションへ書き込み、書き込んだ件数を返す。"""
    if not updates:
        return 0
    db = _get_client()
    detected_at = datetime.now(timezone.utc)
    for u in updates:
        doc = {
            "section": u["section"],
            "title": u["title"],
            "url": u["url"],
            "postedAt": u["posted_at"],
            "detectedAt": detected_at,
        }
        doc_id = doc_id_for(u["url"])
        db.collection("updates").document(doc_id).set(doc, merge=True)
        logging.info("Firestore updates/%s written (%s)", doc_id, u["url"])
    return len(updates)
