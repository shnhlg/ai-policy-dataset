"""Build a lightweight SQLite catalog from local AI-policy raw attachments."""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


POLICY_PREFIX = re.compile(r"^(US-FR|OECD-LINK|EU-CELLAR|UK-MASS|UK)-")
HASH_SUFFIX = re.compile(r"^(?P<policy_id>.+)__[0-9a-f]{16}$", re.IGNORECASE)


def policy_id_from(path: Path) -> str:
    match = HASH_SUFFIX.match(path.stem)
    return match.group("policy_id") if match else path.stem


def source_from(policy_id: str) -> str:
    if policy_id.startswith("US-FR-"):
        return "United States Federal Register"
    if policy_id.startswith("OECD-LINK-"):
        return "OECD.AI Policy Navigator linked source"
    if policy_id.startswith("EU-CELLAR-"):
        return "European Union Cellar/EUR-Lex"
    if policy_id.startswith("UK-MASS-") or policy_id.startswith("UK-"):
        return "United Kingdom government source"
    return "Other"


def iter_policy_files(raw_root: Path):
    for path in sorted(raw_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".html"}:
            continue
        if POLICY_PREFIX.match(path.name):
            yield path


def build(raw_root: Path, database: Path) -> None:
    files = list(iter_policy_files(raw_root))
    if not files:
        raise SystemExit(f"No policy PDF/HTML files found under {raw_root}")
    database.parent.mkdir(parents=True, exist_ok=True)
    database.unlink(missing_ok=True)
    counts = Counter(policy_id_from(path) for path in files)
    with sqlite3.connect(database) as db:
        db.executescript(
            """
            PRAGMA journal_mode=DELETE;
            CREATE TABLE raw_files (
                id INTEGER PRIMARY KEY,
                policy_id TEXT NOT NULL,
                source TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE,
                extension TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified_utc TEXT NOT NULL
            );
            CREATE INDEX idx_raw_files_policy_id ON raw_files(policy_id);
            CREATE INDEX idx_raw_files_source ON raw_files(source);
            CREATE TABLE policies (
                policy_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                attachment_count INTEGER NOT NULL,
                has_pdf INTEGER NOT NULL,
                has_html INTEGER NOT NULL
            );
            CREATE TABLE catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        rows = []
        extensions: dict[str, set[str]] = {}
        for path in files:
            policy_id = policy_id_from(path)
            source = source_from(policy_id)
            extensions.setdefault(policy_id, set()).add(path.suffix.lower())
            stat = path.stat()
            rows.append(
                (
                    policy_id,
                    source,
                    path.relative_to(raw_root).as_posix(),
                    path.suffix.lower(),
                    stat.st_size,
                    datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                )
            )
        db.executemany(
            "INSERT INTO raw_files(policy_id,source,relative_path,extension,size_bytes,modified_utc) VALUES (?,?,?,?,?,?)",
            rows,
        )
        db.executemany(
            "INSERT INTO policies(policy_id,source,attachment_count,has_pdf,has_html) VALUES (?,?,?,?,?)",
            [
                (
                    policy_id,
                    source_from(policy_id),
                    count,
                    int(".pdf" in extensions[policy_id]),
                    int(".html" in extensions[policy_id]),
                )
                for policy_id, count in sorted(counts.items())
            ],
        )
        meta = {
            "catalog_type": "raw_attachment_catalog_not_fulltext_search_database",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "raw_root": str(raw_root.resolve()),
            "file_count": str(len(files)),
            "unique_policy_id_count": str(len(counts)),
            "total_size_bytes": str(sum(path.stat().st_size for path in files)),
        }
        db.executemany("INSERT INTO catalog_meta(key,value) VALUES (?,?)", meta.items())
        db.commit()
    print(f"Built {database}: {len(files):,} files, {len(counts):,} policy IDs")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    build(args.raw_root, args.database)


if __name__ == "__main__":
    main()

