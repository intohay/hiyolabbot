import datetime
import hashlib
import os
import unittest
from unittest.mock import MagicMock, patch

from hiyolabbot import firestore_notifier
from hiyolabbot.watcher import JST


class TestIsEnabled(unittest.TestCase):
    def test_disabled_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(firestore_notifier.is_enabled())

    def test_enabled_when_env_set(self):
        with patch.dict(os.environ, {"HIYOLOVE_SA_KEY": "/tmp/sa.json"}):
            self.assertTrue(firestore_notifier.is_enabled())


class TestDocId(unittest.TestCase):
    def test_news(self):
        self.assertEqual(
            firestore_notifier.doc_id_for(
                "https://hamagishihiyori.fanpla.jp/news/detail/85341"
            ),
            "news-85341",
        )

    def test_blog_trailing_slash(self):
        self.assertEqual(
            firestore_notifier.doc_id_for(
                "https://hamagishihiyori.fanpla.jp/blog/detail/94931/"
            ),
            "blog-94931",
        )

    def test_photo_with_album_segment(self):
        # photo は /photo/331/detail/79175 のように間にセグメントが挟まる
        self.assertEqual(
            firestore_notifier.doc_id_for(
                "https://hamagishihiyori.fanpla.jp/photo/331/detail/79175"
            ),
            "photo-79175",
        )

    def test_fallback_sha1(self):
        url = "https://hamagishihiyori.fanpla.jp/some/other/page"
        expected = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        self.assertEqual(firestore_notifier.doc_id_for(url), expected)


class TestBuildUpdates(unittest.TestCase):
    def test_builds_absolute_urls_with_details(self):
        new_items = {"BLOG": ["/blog/detail/94931"]}
        posted = datetime.datetime(2026, 7, 12, tzinfo=JST)
        details = {"BLOG": {"/blog/detail/94931": {"title": "お気に入りTシャツ🐨", "posted_at": posted}}}
        updates = firestore_notifier.build_updates(
            new_items, details, "https://hamagishihiyori.fanpla.jp/"
        )
        self.assertEqual(
            updates,
            [
                {
                    "section": "BLOG",
                    "title": "お気に入りTシャツ🐨",
                    "url": "https://hamagishihiyori.fanpla.jp/blog/detail/94931",
                    "posted_at": posted,
                }
            ],
        )

    def test_missing_details_become_empty_title(self):
        updates = firestore_notifier.build_updates(
            {"MOVIE": ["/movie/detail/79179"]}, {}, "https://hamagishihiyori.fanpla.jp/"
        )
        self.assertEqual(updates[0]["title"], "")
        self.assertIsNone(updates[0]["posted_at"])


class TestPublishUpdates(unittest.TestCase):
    def test_writes_with_merge_and_doc_id(self):
        mock_db = MagicMock()
        with patch.object(firestore_notifier, "_get_client", return_value=mock_db):
            posted = datetime.datetime(2026, 7, 24, tzinfo=JST)
            count = firestore_notifier.publish_updates(
                [
                    {
                        "section": "INFORMATION",
                        "title": "ゲスト出演のお知らせ",
                        "url": "https://hamagishihiyori.fanpla.jp/news/detail/85341",
                        "posted_at": posted,
                    }
                ]
            )
        self.assertEqual(count, 1)
        mock_db.collection.assert_called_once_with("updates")
        mock_db.collection().document.assert_called_with("news-85341")
        args, kwargs = mock_db.collection().document().set.call_args
        self.assertTrue(kwargs.get("merge"))
        doc = args[0]
        self.assertEqual(doc["section"], "INFORMATION")
        self.assertEqual(doc["title"], "ゲスト出演のお知らせ")
        self.assertEqual(doc["url"], "https://hamagishihiyori.fanpla.jp/news/detail/85341")
        self.assertEqual(doc["postedAt"], posted)
        # detectedAt は UTC の aware datetime（必須フィールド）
        self.assertIsNotNone(doc["detectedAt"].tzinfo)
        # 本文・画像などの余計なフィールドが無いこと
        self.assertEqual(
            set(doc.keys()), {"section", "title", "url", "postedAt", "detectedAt"}
        )

    def test_publish_talk_update_writes_no_content(self):
        # トークは閲覧自体が会員限定。section と検知時刻以外の中身
        # （タイトル・本文・URL）が一切書かれないことを厳密に検証する
        mock_db = MagicMock()
        with patch.object(firestore_notifier, "_get_client", return_value=mock_db):
            firestore_notifier.publish_talk_update("67890")
        mock_db.collection.assert_called_once_with("updates")
        mock_db.collection().document.assert_called_with("talk-67890")
        args, kwargs = mock_db.collection().document().set.call_args
        self.assertTrue(kwargs.get("merge"))
        doc = args[0]
        self.assertEqual(
            set(doc.keys()), {"section", "title", "url", "postedAt", "detectedAt"}
        )
        self.assertEqual(doc["section"], "TALK")
        self.assertEqual(doc["title"], "")
        self.assertEqual(doc["url"], "")
        self.assertIsNone(doc["postedAt"])
        self.assertIsNotNone(doc["detectedAt"].tzinfo)

    def test_empty_updates_do_not_create_client(self):
        with patch.object(firestore_notifier, "_get_client") as mock_get:
            count = firestore_notifier.publish_updates([])
        self.assertEqual(count, 0)
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
