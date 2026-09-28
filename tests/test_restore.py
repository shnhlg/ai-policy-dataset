from __future__ import annotations
import json
import os
import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'viewer'))
import app
from portable import resolve_raw_file, snapshot_is_current

class RestoredViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self,path):
        with urlopen(self.url+path,timeout=30) as r:
            return json.load(r)

    def test_health(self):
        self.assertEqual(self.get('/health')['records'],10542)

    def test_related_and_quarantine(self):
        self.assertEqual(self.get('/api/search?relevance=high')['total'],2739)
        self.assertEqual(self.get('/api/search?relevance=unrelated')['total'],6874)
        self.assertEqual(self.get('/api/search?relevance=review')['total'],929)

    def test_stats_categories(self):
        result=self.get('/api/stats')
        self.assertEqual(result['total'],10542)
        for name in ('政策主题','政策手段','应用领域'):
            self.assertTrue(result['category_facets'][name])

    def test_chinese_and_english_search(self):
        for term in ('人工智能','artificial intelligence'):
            self.assertGreater(self.get('/api/search?'+urlencode({'q':term}))['total'],0)

    def test_pdf_and_country(self):
        stats=self.get('/api/stats')
        result=self.get('/api/search?file_type=pdf')
        self.assertEqual(result['total'],stats['pdf_count'])
        country=stats['facets']['country_or_org'][0]['value']
        items=self.get('/api/search?'+urlencode({'country':country}))['items']
        self.assertTrue(all(x['country_or_org']==country for x in items))

    def test_category_filter(self):
        stats=self.get('/api/stats')
        for dimension,param in [('政策主题','topic_category'),('政策手段','instrument_category'),('应用领域','sector_category')]:
            facet=next(x for x in stats['category_facets'][dimension] if x['count'])
            result=self.get('/api/search?'+urlencode({param:facet['value']}))
            self.assertEqual(result['total'],facet['count'])

    def test_translated_title_and_body(self):
        with sqlite3.connect(ROOT/'viewer/policy_search.db') as c:
            pid=c.execute("select policy_id from policies where title_zh<>'' and language='en' and body_offset is not null limit 1").fetchone()[0]
        detail=self.get('/api/policies/'+quote(pid))
        self.assertTrue(detail['title_zh'])
        self.assertTrue(detail['title_original'])
        body=self.get('/api/policies/'+quote(pid)+'/body?limit=1000')
        self.assertTrue(body['text'])
        if body['has_more']:
            continuation=self.get('/api/policies/'+quote(pid)+'/body?limit=1000&offset=1000')
            self.assertEqual(continuation['offset'],1000)

    def test_raw_supplemental_chinese(self):
        with urlopen(self.url+'/api/policies/CN-00001/raw',timeout=30) as r:
            self.assertEqual(r.status,200)
            self.assertIn('sandbox',r.headers.get('Content-Security-Policy',''))
            self.assertTrue(r.read(100))

    def test_bad_parameters(self):
        for path in ('/api/search?page=0','/api/search?file_type=exe','/api/search?relevance=wrong','/%2e%2e/README.md'):
            with self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertIn(error.exception.code,(400,404))

    def test_raw_path_safety(self):
        for raw in ('../README.md','data/raw/../../README.md','C:/secret.txt','data/processed/policy_fulltexts.jsonl'):
            self.assertIsNone(resolve_raw_file(raw))

    def test_frontend_assets(self):
        for path in ('/','/app.js','/styles.css'):
            with urlopen(self.url+path) as r:
                self.assertEqual(r.status,200)
                self.assertGreater(len(r.read()),100)

if __name__=='__main__':
    unittest.main()
