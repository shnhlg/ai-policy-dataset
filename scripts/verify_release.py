"""Verify repository structure, SQLite databases, and common secret leaks."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = {
    "OpenAI-style key": re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    "Bearer token": re.compile(rb"Authorization\s*[:=]\s*Bearer\s+[A-Za-z0-9._-]{20,}", re.I),
}
TEXT_EXTENSIONS = {".py", ".js", ".css", ".html", ".md", ".json", ".toml", ".yaml", ".yml", ".ps1", ".txt"}


def check_database(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                errors.append(f"{path}: integrity_check={result}")
    except sqlite3.Error as exc:
        errors.append(f"{path}: SQLite error: {exc}")
    return errors


def main() -> int:
    errors: list[str] = []
    required = [ROOT / "README.md", ROOT / ".gitignore", ROOT / ".gitattributes"]
    for path in required:
        if not path.is_file():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")
    databases = list(ROOT.rglob("*.db")) + list(ROOT.rglob("*.sqlite")) + list(ROOT.rglob("*.sqlite3"))
    if not databases:
        errors.append("No SQLite database found")
    for database in databases:
        errors.extend(check_database(database))
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        data = path.read_bytes()
        if path.name == ".env.example":
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                errors.append(f"Potential {label} in {path.relative_to(ROOT)}")
    oversized = [path for path in ROOT.rglob("*") if path.is_file() and path.stat().st_size > 100 * 1024 * 1024]
    tracked_patterns = {".db", ".sqlite", ".sqlite3", ".parquet", ".zip"}
    for path in oversized:
        if path.suffix.lower() not in tracked_patterns:
            errors.append(f"File over 100 MiB is not covered by expected LFS rule: {path.relative_to(ROOT)}")
    if errors:
        print("RELEASE CHECK FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("RELEASE CHECK PASSED")
    print(f"- SQLite databases: {len(databases)}")
    print(f"- Files over 100 MiB: {len(oversized)}")
    print("- No common API/token pattern detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())

