"""Validate a release against its manifest, CSV and every body record."""
from __future__ import annotations
import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'viewer'))


def verify(check_hashes=True):
    from indexer import CSV_PATH, FULLTEXT_PATH, DB_PATH
    from portable import resolve_raw_file
    manifest = json.loads((ROOT / 'dataset_manifest.json').read_text(encoding='utf-8'))
    if check_hashes:
        for item in manifest['files']:
            path = CSV_PATH.parent / item['name']
            assert path.stat().st_size == item['bytes'], item['name']
            with path.open('rb') as handle:
                assert hashlib.file_digest(handle, 'sha256').hexdigest() == item['sha256'], item['name']
    with CSV_PATH.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        assert len(reader.fieldnames) == len(set(reader.fieldnames)), 'Duplicate CSV columns'
        csv_ids = [row['policy_id'] for row in reader]
    assert len(csv_ids) == len(set(csv_ids)) == manifest['records']
    source = sqlite3.connect(DB_PATH.as_uri() + '?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    memory = sqlite3.connect(':memory:')
    try:
        source.backup(memory)
        assert memory.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        memory.execute("INSERT INTO policy_fts(policy_fts) VALUES ('integrity-check')")
        rows = {row['policy_id']: row for row in source.execute('SELECT * FROM policies')}
        assert set(rows) == set(csv_ids)
        assert dict(source.execute('SELECT relevance_level,COUNT(*) FROM policies GROUP BY relevance_level')) == manifest['relevance_counts']
        seen = set()
        with FULLTEXT_PATH.open('rb', buffering=1024 * 1024) as handle:
            while True:
                offset = handle.tell()
                line = handle.readline()
                if not line: break
                record = json.loads(line)
                pid = record['policy_id']
                assert pid in rows and pid not in seen, pid
                row = rows[pid]
                text = str(record.get('fulltext', ''))
                assert (row['body_offset'], row['body_bytes']) == (offset, len(line)), pid
                assert len(text) == row['fulltext_char_count'], pid
                if row['content_extraction_status'] in {'non_body','mixed_source','ocr_required'}:
                    assert not text.strip(), pid
                seen.add(pid)
        assert seen == set(rows)
        connected = sum(resolve_raw_file(row['raw_file']) is not None for row in rows.values())
        result = {'records': len(rows), 'body_positions_verified': len(seen), 'raw_available': connected,
                  'raw_missing': len(rows) - connected, 'sqlite': sqlite3.sqlite_version,
                  'fts_integrity': 'ok', 'hashes_checked': check_hashes}
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return result
    finally:
        memory.close(); source.close()


if __name__ == '__main__':
    from prepare_runtime import prepare
    prepare()
    verify()
