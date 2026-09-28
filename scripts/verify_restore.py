"""Offline integrity, body-offset and raw-file reference checks."""
from __future__ import annotations
import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'viewer'))
from portable import resolve_raw_file

def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()

def verify(check_hashes=True):
    manifest = ROOT/'migration_manifest.json'
    if check_hashes:
        entries = json.loads(manifest.read_text(encoding='utf-8'))
        for entry in entries:
            path = (ROOT/entry['path']).resolve()
            assert ROOT in path.parents, entry['path']
            assert path.is_file() and path.stat().st_size == entry['bytes'], entry['path']
            assert digest(path) == entry['sha256'], entry['path']
        print(f'File SHA256 verified: {len(entries)}', flush=True)
    with sqlite3.connect((ROOT/'viewer/policy_search.db').as_uri()+'?mode=ro',uri=True) as db:
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
        rows = db.execute('select policy_id,body_offset,body_bytes,raw_file from policies order by body_offset').fetchall()
        assert len(rows) == 10542, len(rows)
        body_count = 0
        with (ROOT/'data/processed/policy_fulltexts.jsonl').open('rb') as f:
            for pid,offset,size,raw in rows:
                assert offset is not None and size > 0, pid
                f.seek(offset)
                record = json.loads(f.read(size))
                assert record.get('policy_id') == pid, pid
                assert str(record.get('fulltext','')).strip(), pid
                body_count += 1
        counts = dict(db.execute('select relevance_level,count(*) from policies group by relevance_level'))
        categories = db.execute('select count(*) from categories').fetchone()[0]
        linked = sum(resolve_raw_file(raw) is not None for _,_,_,raw in rows)
    with (ROOT/'data/processed/title_translation_review_2674.csv').open(encoding='utf-8-sig',newline='') as f:
        reviewed = sum(1 for _ in csv.DictReader(f))
    assert reviewed == 2674, reviewed
    result = {'records':len(rows),'body_links_verified':body_count,'relevance':counts,'categories':categories,
              'contextual_title_reviews':reviewed,'raw_connected':linked,'raw_total':len(rows)}
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    if linked < len(rows):
        print('部分原始附件未连接：运行 python scripts/configure_raw.py。正文及检索不受影响。',flush=True)
    return result

if __name__ == '__main__':
    verify()
