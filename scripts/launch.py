"""Launch the restored original viewer without installing ML dependencies."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Please install Python 3.11 or newer (3.13 recommended).')
    with sqlite3.connect(':memory:') as db:
        try:
            db.execute("CREATE VIRTUAL TABLE test USING fts5(text, tokenize='trigram')")
        except sqlite3.Error as exc:
            raise SystemExit('Python SQLite must support FTS5 trigram. Install Python 3.13.') from exc
    for name in ('data/processed/ai_policies_content_master.csv',
                 'data/processed/policy_fulltexts.jsonl', 'viewer/static/index.html'):
        if not (ROOT / name).is_file():
            raise SystemExit(f'Missing file: {name}. Fully extract the migration ZIP first.')
    sys.path.insert(0, str(ROOT / 'viewer'))
    from app import main as run_viewer
    run_viewer()

if __name__ == '__main__':
    main()
