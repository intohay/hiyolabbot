import json
import unittest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import tempfile
import os

# テスト用に一時ディレクトリを使用
test_dir = tempfile.mkdtemp()
os.chdir(test_dir)

from src.hiyolabbot.talk_watcher import (
    make_talk_snapshot,
    diff_talk,
    load_talk_previous,
    save_talk_snapshot,
    TALK_SNAPSHOT_FILE
)


class TestTalkWatcher(unittest.TestCase):
    
    def setUp(self):
        # 各テストの前にスナップショットファイルを削除
        if TALK_SNAPSHOT_FILE.exists():
            TALK_SNAPSHOT_FILE.unlink()
    
    def test_make_talk_snapshot(self):
        """スナップショット作成のテスト"""
        comment_ids = ["12345", "12346", "12347"]
        
        snapshot = make_talk_snapshot(comment_ids)
        
        self.assertIn("talk_comments", snapshot)
        self.assertEqual(snapshot["talk_comments"], ["12345", "12346", "12347"])
    
    def test_make_talk_snapshot_with_unsorted_ids(self):
        """ソートされていないIDでのスナップショット作成テスト"""
        comment_ids = ["12347", "12345", "12346"]
        
        snapshot = make_talk_snapshot(comment_ids)
        
        # 数値順にソートされることを確認
        self.assertEqual(snapshot["talk_comments"], ["12345", "12346", "12347"])
    
    def test_diff_talk_initial_scan(self):
        """初回スキャン時の差分検出テスト"""
        curr = {"talk_comments": ["12345", "12346"]}
        
        result = diff_talk(None, curr)
        self.assertEqual(result, ["トーク初回スキャン（スナップショット作成）"])
    
    def test_diff_talk_with_new_comments(self):
        """新しいコメントがある場合の差分検出テスト"""
        prev = {"talk_comments": ["12345", "12346"]}
        curr = {"talk_comments": ["12345", "12346", "12347", "12348"]}
        
        result = diff_talk(prev, curr)
        self.assertEqual(result, ["新しいトーク: 2件のメッセージ"])
    
    def test_diff_talk_no_changes(self):
        """変更なしの場合のテスト"""
        prev = {"talk_comments": ["12345", "12346"]}
        curr = {"talk_comments": ["12345", "12346"]}
        
        result = diff_talk(prev, curr)
        self.assertEqual(result, [])
    
    def test_save_and_load_talk_snapshot(self):
        """スナップショットの保存と読み込みテスト"""
        snapshot = {"talk_comments": ["12345", "12346", "12347"]}
        
        save_talk_snapshot(snapshot)
        self.assertTrue(TALK_SNAPSHOT_FILE.exists())
        
        loaded = load_talk_previous()
        self.assertEqual(loaded, snapshot)
    
    def test_diff_detection_after_new_talk(self):
        """トーク追加後の差分検出シミュレーションテスト"""
        # 初回スキャン
        initial_comment_ids = ["12345", "12346", "12347"]
        initial_snapshot = make_talk_snapshot(initial_comment_ids)
        save_talk_snapshot(initial_snapshot)
        
        # 新しいトークが追加された状態をシミュレート
        updated_comment_ids = ["12345", "12346", "12347", "12348", "12349"]
        updated_snapshot = make_talk_snapshot(updated_comment_ids)
        
        # 差分を検出
        prev = load_talk_previous()
        changes = diff_talk(prev, updated_snapshot)
        
        # 2件の新しいメッセージが検出されることを確認
        self.assertEqual(changes, ["新しいトーク: 2件のメッセージ"])
        
        # 更新後のスナップショットを保存
        save_talk_snapshot(updated_snapshot)
        
        # 再度同じ状態でチェックした場合、変更なしになることを確認
        prev = load_talk_previous()
        changes = diff_talk(prev, updated_snapshot)
        self.assertEqual(changes, [])
    
    @patch('src.hiyolabbot.talk_watcher.async_playwright')
    async def test_extract_comment_ids(self, mock_playwright):
        """コメントID抽出のテスト"""
        # Playwrightのモックセットアップ
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_p = AsyncMock()
        
        # モック要素の作成
        mock_elements = []
        for comment_id in ["comment-body-12345", "comment-body-12346", "comment-body-12347"]:
            element = AsyncMock()
            element.get_attribute.return_value = comment_id
            mock_elements.append(element)
        
        mock_page.query_selector_all.return_value = mock_elements
        mock_page.url = "https://hamagishihiyori.fanpla.jp/community/detail/55/?f=artist"
        
        mock_playwright.return_value.__aenter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # SESSION_FILE が存在しない場合のテスト
        from src.hiyolabbot.talk_watcher import extract_comment_ids, SESSION_FILE
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
        
        # テスト実行
        result = await extract_comment_ids("test_id", "test_password")
        
        # アサーション
        self.assertEqual(result, ["12345", "12346", "12347"])
        mock_page.query_selector_all.assert_called_with('#chat-area ul li div p[id^="comment-body-"]')
    
    @patch('src.hiyolabbot.talk_watcher.async_playwright')
    async def test_check_talk_updates_integration(self, mock_playwright):
        """check_talk_updates の統合テスト"""
        # Playwrightのモックセットアップ
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_p = AsyncMock()
        
        # 初回スキャンのモック
        initial_elements = []
        for comment_id in ["comment-body-12345", "comment-body-12346"]:
            element = AsyncMock()
            element.get_attribute.return_value = comment_id
            initial_elements.append(element)
        
        mock_page.query_selector_all.return_value = initial_elements
        mock_page.url = "https://hamagishihiyori.fanpla.jp/community/detail/55/?f=artist"
        
        mock_playwright.return_value.__aenter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        from src.hiyolabbot.talk_watcher import check_talk_updates
        
        # 初回スキャン
        changes = await check_talk_updates("test_id", "test_password")
        self.assertEqual(changes, ["トーク初回スキャン（スナップショット作成）"])
        
        # 新しいトークが追加された状態をシミュレート
        updated_elements = []
        for comment_id in ["comment-body-12345", "comment-body-12346", "comment-body-12347"]:
            element = AsyncMock()
            element.get_attribute.return_value = comment_id
            updated_elements.append(element)
        
        mock_page.query_selector_all.return_value = updated_elements
        
        # 2回目のスキャン
        changes = await check_talk_updates("test_id", "test_password")
        self.assertEqual(changes, ["新しいトーク: 1件のメッセージ"])


if __name__ == '__main__':
    unittest.main()