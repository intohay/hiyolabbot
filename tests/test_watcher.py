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

    def test_save_snapshot(self):
        # save_snapshot は一時ファイル経由で書くため、実ファイルで検証する
        import json
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = pathlib.Path(tmpdir) / 'snapshot.json'
            with patch('hiyolabbot.watcher.SNAPSHOT_FILE', snapshot_path):
                snap = {'INFORMATION': ['/news/detail/85341']}
                watcher.save_snapshot(snap)
                self.assertEqual(
                    json.loads(snapshot_path.read_text(encoding='utf-8')), snap
                )

    

    # 実サイトの DOM 構造（li > a > div.block--txt > p.date / p.tit）を模したフィクスチャ
    SECTION_HTML = '''
    <section id="news">
        <p class="list__more"><a href="/news/1">VIEW ALL</a></p>
        <ul>
            <li class="list__item">
                <a href="/news/detail/85341">
                    <div class="block--txt">
                        <p class="date">2026.07.24</p>
                        <p class="tit">ゲスト出演のお知らせ</p>
                    </div>
                </a>
            </li>
            <li class="list__item">
                <a href="/news/detail/85344/">
                    <div class="block--txt">
                        <p class="date">2026.07.22</p>
                        <p class="tit">『あにレコTV』出演のお知らせ</p>
                    </div>
                </a>
            </li>
        </ul>
    </section>
    '''

    def test_extract_item_details(self):
        soup = BeautifulSoup(self.SECTION_HTML, "lxml")
        details = watcher.extract_item_details(soup.select_one("section#news"))
        # VIEW ALL のような detail 系以外のリンクは含まれない
        self.assertEqual(
            set(details.keys()), {"/news/detail/85341", "/news/detail/85344"}
        )
        item = details["/news/detail/85341"]
        self.assertEqual(item["title"], "ゲスト出演のお知らせ")
        self.assertEqual(
            item["posted_at"],
            watcher.datetime.datetime(2026, 7, 24, tzinfo=watcher.JST),
        )
        # 末尾スラッシュ付き href も正規化されて同じキー形式になる
        self.assertEqual(
            details["/news/detail/85344"]["title"], "『あにレコTV』出演のお知らせ"
        )

    def test_extract_item_details_fallbacks(self):
        # p.tit / p.date が無い場合: タイトルは a のテキスト、日付は None
        html = '''
        <section id="news">
            <a href="/news/detail/85341">お知らせ1</a>
        </section>
        '''
        soup = BeautifulSoup(html, "lxml")
        details = watcher.extract_item_details(soup.select_one("section#news"))
        item = details["/news/detail/85341"]
        self.assertEqual(item["title"], "お知らせ1")
        self.assertIsNone(item["posted_at"])

    def test_extract_item_details_none_section(self):
        self.assertEqual(watcher.extract_item_details(None), {})

    def test_diff_items_returns_new_hrefs(self):
        prev = {"INFORMATION": ["/news/detail/85341"], "BLOG": ["/blog/detail/94931"]}
        curr = {
            "INFORMATION": ["/news/detail/85344", "/news/detail/85341"],
            "BLOG": ["/blog/detail/94931"],
        }
        new_items = watcher.diff_items(prev, curr)
        self.assertEqual(new_items, {"INFORMATION": ["/news/detail/85344"]})

    def test_diff_items_first_scan_returns_empty(self):
        # 初回スキャン（prev なし）では何も返さない → Firestore へ書かれない
        self.assertEqual(watcher.diff_items(None, {"INFORMATION": ["/news/detail/85341"]}), {})

    def test_diff_items_old_format_returns_empty(self):
        # 旧形式（ハッシュ文字列）のスナップショットも初回扱い
        prev = {"INFORMATION": "abcdef123456"}
        self.assertEqual(watcher.diff_items(prev, {"INFORMATION": ["/news/detail/85341"]}), {})

    def test_diff_items_no_changes_returns_empty(self):
        snap = {"INFORMATION": ["/news/detail/85341"]}
        self.assertEqual(watcher.diff_items(snap, snap), {})

    def test_diff_detects_new_a_link_in_section(self):
        # 前のHTML: aタグ1つ
        html_prev = '''
        <section id="news">
            <a href="/news/12445">お知らせ1</a>
        </section>
        '''
        # 現在のHTML: aタグ2つ（新規追加）
        html_curr = '''
        <section id="news">
            <a href="/news/12445">お知らせ1</a>
            <a href="/news/12446">お知らせ2</a>
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