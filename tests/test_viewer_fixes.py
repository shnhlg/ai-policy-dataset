import json
import sqlite3
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer'))
from app import byte_range, Handler, dataset_version
from indexer import DB_PATH, index_is_current
from quality import clean_summary, country, language


class ViewerFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def get(self, path):
        with urlopen(self.url + path, timeout=30) as response:
            return json.load(response)

    def test_literal_percent(self):
        with sqlite3.connect(DB_PATH) as db:
            expected = db.execute("SELECT COUNT(*) FROM policies WHERE instr(title_original,'%') OR instr(title_zh,'%') OR instr(country_or_org,'%') OR instr(issuer,'%') OR instr(content_summary_original,'%')").fetchone()[0]
        self.assertEqual(self.get('/api/search?q=%25')['total'], expected)

    def test_available_pdf_filter(self):
        result = self.get('/api/search?file_type=pdf')
        self.assertGreater(result['total'], 0)
        self.assertTrue(all(row['raw_available'] and row['raw_is_pdf'] for row in result['items']))

    def test_missing_raw_detail(self):
        row = self.get('/api/search?file_type=missing')['items'][0]
        detail = self.get('/api/policies/' + row['policy_id'])
        self.assertFalse(detail['raw_available'])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + '/api/policies/' + row['policy_id'] + '/raw')
        self.assertEqual(error.exception.code, 404)

    def test_gb_standard_is_not_an_empty_file(self):
        detail = self.get('/api/policies/CN-00010')
        self.assertTrue(detail['raw_available'])
        self.assertTrue(detail['raw_is_pdf'])
        self.assertFalse(detail['body_available'])
        self.assertEqual(detail['content_extraction_status'], 'ocr_required')

    def test_range_and_cache(self):
        url = self.url + '/api/policies/CN-00010/raw'
        with urlopen(Request(url, headers={'Range': 'bytes=0-1023'})) as response:
            self.assertEqual(response.status, 206)
            data = response.read()
            self.assertEqual(len(data), 1024)
            self.assertTrue(data.startswith(b'%PDF'))
            etag = response.headers['ETag']
            self.assertTrue(response.headers['Content-Range'].startswith('bytes 0-1023/'))
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(url, headers={'If-None-Match': etag}))
        self.assertEqual(error.exception.code, 304)
        with urlopen(Request(url, method='HEAD')) as response:
            self.assertEqual(response.read(), b'')
            self.assertGreater(int(response.headers['Content-Length']), 1024)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(url, headers={'Range': 'bytes=999999999-'}))
        self.assertEqual(error.exception.code, 416)

    def test_quarantined_body_is_empty(self):
        for status in ('non_body', 'mixed_source', 'ocr_required'):
            item = self.get('/api/search?body_status=' + status)['items'][0]
            body = self.get('/api/policies/' + item['policy_id'] + '/body')
            self.assertEqual(body['text'], '')

    def test_hidden_navigation_summary(self):
        with sqlite3.connect(DB_PATH) as db:
            count = db.execute("SELECT COUNT(*) FROM policies WHERE summary_status='navigation_review'").fetchone()[0]
            visible = db.execute("SELECT COUNT(*) FROM policies WHERE summary_status='navigation_review' AND content_summary_original<>''").fetchone()[0]
        self.assertGreater(count, 0)
        self.assertEqual(visible, 0)

    def test_index_current_and_valid(self):
        self.assertTrue(index_is_current())
        source = sqlite3.connect(DB_PATH.as_uri() + '?mode=ro', uri=True)
        copy = sqlite3.connect(':memory:')
        try:
            source.backup(copy)
            self.assertEqual(copy.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            copy.execute("INSERT INTO policy_fts(policy_fts) VALUES ('integrity-check')")
        finally:
            copy.close(); source.close()

    def test_stats_cache(self):
        first = Handler.statistics(dataset_version())
        second = Handler.statistics(dataset_version())
        self.assertIs(first, second)
        self.assertEqual(first['raw_available'] + first['raw_missing'], first['total'])


class PureFunctionTests(unittest.TestCase):
    def test_range_parser(self):
        self.assertEqual(byte_range('bytes=0-9', 100), (0, 9))
        self.assertEqual(byte_range('bytes=-10', 100), (90, 99))
        self.assertEqual(byte_range('bytes=99-', 100), (99, 99))
        for value in ('bytes=-0', 'bytes=100-', 'bytes=9-2', 'bytes=0-1,3-4', 'bytes=-'):
            with self.assertRaises(ValueError): byte_range(value, 100)

    def test_cleanup_does_not_invent_summary(self):
        self.assertEqual(clean_summary('Accept additional cookies Policy'), ('', 'navigation_review'))
        self.assertEqual(clean_summary('Actual policy text'), ('Actual policy text', 'available'))
        self.assertEqual(clean_summary('Old text', 'non_body')[0], '')
        self.assertEqual(country('China (People’s Republic of)'), '中国')
        self.assertEqual(language('eng'), 'en')
