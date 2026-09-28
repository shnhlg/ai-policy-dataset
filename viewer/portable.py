"""Portable raw-file lookup and content-based index snapshot validation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'viewer' / 'portable_index.json'


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def snapshot_is_current() -> bool:
    """ZIP extraction changes mtimes, but not the index/input contents."""
    try:
        entries = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        if not entries:
            return False
        for item in entries:
            path = (ROOT / item['path']).resolve()
            if ROOT not in path.parents or path.stat().st_size != item['bytes']:
                return False
            if digest(path) != item['sha256']:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def external_raw_roots() -> list[Path]:
    roots = []
    configured = os.environ.get('AI_POLICY_RAW_ROOT', '').strip()
    config = ROOT / 'raw-root.txt'
    if not configured and config.is_file():
        configured = config.read_text(encoding='utf-8-sig').strip()
    if configured:
        candidate = Path(configured).expanduser()
        roots.append((candidate if candidate.is_absolute() else ROOT / candidate).resolve())
    roots.append((ROOT.parent / 'data' / 'raw').resolve())
    return roots


def resolve_raw_file(raw: str) -> Path | None:
    relative = PurePosixPath(raw.replace('\\', '/'))
    parts = relative.parts
    if relative.is_absolute() or '..' in parts or ':' in raw:
        return None
    if not (parts[:2] == ('data', 'raw') or parts[:3] == ('data', 'official_zh', 'raw')):
        return None
    source_root = Path(os.environ.get('AI_POLICY_SOURCE_ROOT', ROOT)).resolve()
    for base in (ROOT, source_root):
        local = (base / Path(*parts)).resolve()
        if base in local.parents and local.is_file():
            return local
        if parts[:2] == ('data', 'raw'):
            supplemental = (base / 'data' / 'official_zh' / 'raw' / relative.name).resolve()
            if base in supplemental.parents and supplemental.is_file():
                return supplemental
    # Existing data package contains a flat raw directory. Never trust an arbitrary path.
    for root in external_raw_roots():
        candidate = (root / relative.name).resolve()
        if root in candidate.parents and candidate.is_file():
            return candidate
    return None
