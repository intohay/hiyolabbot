import hashlib
import re
import unittest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

from hiyolabbot import watcher


class TestWatcher(unittest.TestCase):
    @patch('hiyolabbot.watcher.requests.get')
    def test_fetch_html(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = '<html></html>'
        mock_get.return_value = mock_response

        soup = watcher.fetch_html()
        self.assertIsNotNone(soup)

    

   

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

    

    def test_diff_detects_new_a_link_in_section(self):
        # 前のHTML: aタグ1つ
        html_prev = '''
        <section id="news">
            <a href="/news/1">お知らせ1</a>
        </section>
        '''
        # 現在のHTML: aタグ2つ（新規追加）
        html_curr = '''
        <section id="news">
            <a href="/news/1">お知らせ1</a>
            <a href="/news/2">お知らせ2</a>
        </section>
        '''
        soup_prev = BeautifulSoup(html_prev, "lxml")
        soup_curr = BeautifulSoup(html_curr, "lxml")
        snap_prev = watcher.make_snapshot(soup_prev)
        snap_curr = watcher.make_snapshot(soup_curr)
        changes = watcher.diff(snap_prev, snap_curr)
        self.assertIn("INFORMATION", changes)

if __name__ == '__main__':
    unittest.main() 