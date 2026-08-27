"""Create a portable SHA-256 manifest for the repository package."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "RELEASE_MANIFEST.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


files = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or path == OUTPUT or ".git" in path.parts or "__pycache__" in path.parts:
        continue
    files.append(
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    )

payload = {
    "package": "ai-policy-dataset",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "file_count": len(files),
    "total_size_bytes": sum(item["size_bytes"] for item in files),
    "files": files,
}
OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {OUTPUT} with {len(files)} entries")

