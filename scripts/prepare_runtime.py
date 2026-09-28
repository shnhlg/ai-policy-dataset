"""Build and validate a release in the Linux volume before switching CURRENT."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def activate(release: Path) -> None:
    os.environ['AI_POLICY_DATA_DIR'] = str(release / 'processed')
    os.environ['AI_POLICY_DB'] = str(release / 'policy_search.db')


def prepare() -> Path | None:
    configured = os.environ.get('AI_POLICY_RUNTIME')
    if not configured:
        return None
    runtime = Path(configured)
    runtime.mkdir(parents=True, exist_ok=True)
    # The container is Linux; serialize preparation from concurrent compose runs.
    import fcntl
    with (runtime / 'prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return prepare_locked(runtime)


def prepare_locked(runtime: Path) -> Path:
    selected = os.environ.get('AI_POLICY_RELEASE', '').strip()
    if selected:
        if len(selected) != 20 or any(c not in '0123456789abcdef' for c in selected):
            raise ValueError('运行版本编号无效')
        release = runtime / 'releases' / selected
        if not (release / 'ready.json').is_file():
            raise ValueError('所选版本不存在或未完成校验')
        activate(release)
        return release
    source = Path(os.environ.get('AI_POLICY_SOURCE_ROOT', ROOT))
    inputs = [source / 'data' / 'processed' / name for name in
              ('ai_policies_content_master.csv', 'policy_fulltexts.jsonl')]
    for path in inputs:
        if not path.is_file() or path.stat().st_size < 1000:
            raise RuntimeError(f'数据文件缺失或尚未下载 Git LFS 内容：{path.name}')
    stamp = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in inputs]
    code_hash = hashlib.sha256()
    for path in sorted((ROOT / 'viewer').glob('*.py')) + sorted((ROOT / 'viewer').glob('*.jsonl')):
        code_hash.update(path.name.encode())
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                code_hash.update(block)
    raw_stamp = []
    for directory in (source / 'data' / 'raw', source / 'data' / 'official_zh' / 'raw'):
        if directory.is_dir():
            raw_stamp.extend((str(p.relative_to(source)), p.stat().st_size, p.stat().st_mtime_ns)
                             for p in sorted(directory.rglob('*')) if p.is_file())
    raw_hash = hashlib.sha256(json.dumps(raw_stamp).encode()).hexdigest()
    identity = {'inputs': stamp, 'code': code_hash.hexdigest(), 'sqlite': sqlite3.sqlite_version, 'raw_inventory': raw_hash}
    version = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    releases = runtime / 'releases'
    releases.mkdir(exist_ok=True)
    release = releases / version
    if not (release / 'ready.json').is_file():
        with tempfile.TemporaryDirectory(prefix='building-', dir=releases) as staging:
            stage = Path(staging)
            (stage / 'processed').mkdir()
            hashes = {}
            for path in inputs:
                print(f'复制运行数据：{path.name}', flush=True)
                target = stage / 'processed' / path.name
                sha = hashlib.sha256()
                with path.open('rb') as src, target.open('wb') as dst:
                    for block in iter(lambda: src.read(4 * 1024 * 1024), b''):
                        sha.update(block)
                        dst.write(block)
                shutil.copystat(path, target)
                hashes[path.name] = sha.hexdigest()
            if stamp != [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in inputs]:
                raise RuntimeError('复制期间源数据发生变化，未发布，请在采集结束后重试。')
            activate(stage)
            sys.path.insert(0, str(ROOT / 'viewer'))
            from indexer import build_index
            build_index()
            # Later callers must import paths for the published directory, not staging.
            sys.modules.pop('indexer', None)
            with sqlite3.connect(stage / 'policy_search.db') as db:
                records = db.execute('SELECT COUNT(*) FROM policies').fetchone()[0]
                counts = dict(db.execute('SELECT relevance_level,COUNT(*) FROM policies GROUP BY relevance_level'))
            ready = {**identity, 'version': version, 'sha256': hashes, 'records': records, 'relevance_counts': counts}
            (stage / 'ready.json').write_text(json.dumps(ready, ensure_ascii=False, indent=2), encoding='utf-8')
            # A release becomes visible only after both data files and its index pass validation.
            stage.rename(release)
    activate(release)
    pending = runtime / 'CURRENT.pending'
    pending.write_text(version, encoding='ascii')
    os.replace(pending, runtime / 'CURRENT')
    print(f'运行数据版本：{version}', flush=True)
    return release


if __name__ == '__main__':
    prepare()
