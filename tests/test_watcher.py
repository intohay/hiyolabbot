import hashlib
import re
import unittest
from unittest.mock import MagicMock, patch

from hiyolabbot import watcher


class TestWatcher(unittest.TestCase):
    @patch('hiyolabbot.watcher.requests.get')
    def test_fetch_html(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = '<html></html>'
        mock_get.return_value = mock_response

        soup = watcher.fetch_html()
        self.assertIsNotNone(soup)

    def test_hash_text(self):
        node = MagicMock()
        node.get_text.return_value = 'Example text 123'
        result = watcher.hash_text(node)
        self.assertIsNotNone(result)

    def test_hash_text_different_texts(self):
        node1 = MagicMock()
        node1.get_text.return_value = 'Example text 123'
        node2 = MagicMock()
        node2.get_text.return_value = 'Different text 456'
        
        hash1 = watcher.hash_text(node1)
        hash2 = watcher.hash_text(node2)
        
        self.assertNotEqual(hash1, hash2, "異なるテキストに対して同じハッシュ値が返されました")

    def test_hash_text_ignore_numbers(self):
        node1 = MagicMock()
        node1.get_text.return_value = 'Example text 123'
        node2 = MagicMock()
        node2.get_text.return_value = 'Example text 456'
        
        hash1 = watcher.hash_text(node1)
        hash2 = watcher.hash_text(node2)
        
        self.assertEqual(hash1, hash2, "数字が異なるテキストに対して異なるハッシュ値が返されました")


    def test_make_snapshot(self):
        # モックされたBeautifulSoupオブジェクトを作成
        soup = MagicMock()
        
        # 各セレクタに対するモックされたノードを設定
        selectors = {
            "section#news": "INFORMATION text 123",
            "section#blog": "BLOG text 456",
            "section#movie": "MOVIE text 789",
            "section#photo": "PHOTO text 012",
            "section#qa": "Q&A text 345"
        }
        
        # select_oneの返り値をセレクタごとに設定
        def select_one_side_effect(selector):
            node = MagicMock()
            node.get_text.return_value = selectors[selector]
            return node
        
        soup.select_one.side_effect = select_one_side_effect
        
        # スナップショットを作成
        result = watcher.make_snapshot(soup)
        
        # 各セレクタに対する期待されるハッシュ値を確認
        for selector, label in watcher.TRACK_SELECTORS.items():
            expected_hash = hashlib.sha256(re.sub(r'\d+', '', selectors[selector]).encode()).hexdigest()
            self.assertEqual(result[label], expected_hash, f"{label}のハッシュが一致しません")

    @patch('hiyolabbot.watcher.SNAPSHOT_FILE')
    def test_load_previous(self, mock_snapshot_file):
        mock_snapshot_file.exists.return_value = True
        mock_snapshot_file.read_text.return_value = '{}'
        result = watcher.load_previous()
        self.assertIsInstance(result, dict)

    @patch('hiyolabbot.watcher.SNAPSHOT_FILE')
    def test_save_snapshot(self, mock_snapshot_file):
        snap = {'key': 'value'}
        watcher.save_snapshot(snap)
        mock_snapshot_file.write_text.assert_called_once()

    def test_diff(self):
        prev = {'key': 'old_value'}
        curr = {'key': 'new_value'}
        result = watcher.diff(prev, curr)
        self.assertIn('key', result)

if __name__ == '__main__':
    unittest.main() 