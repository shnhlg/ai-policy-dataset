"""Remove explicitly rejected records from all canonical dataset outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
POLICY_IDS = {"US-FR-AI16-016-0001", "US-FR-AI16-016-0006"}
CSV_FILES = [
    "ai_policies_master.csv", "ai_policies_content_master.csv",
    "content_extraction_failures.csv", "ai_policies_enriched.csv",
    "content_extraction_retry_success.csv", "content_extraction_retry_failures.csv",
]
JSONL_FILES = ["policy_fulltexts.jsonl", "policy_fulltexts_retry.jsonl"]


def filter_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        kept = [row for row in reader if row.get("policy_id") not in POLICY_IDS]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(kept)
    return kept


def main() -> int:
    removed_raw: set[Path] = set()
    raw_paths: set[Path] = set()
    with (DATA / "content_extraction_failures.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("policy_id") in POLICY_IDS and row.get("raw_file"):
                raw_paths.add(ROOT / row["raw_file"])
    for name in CSV_FILES:
        path = DATA / name
        if path.exists():
            filter_csv(path)
    for raw_path in raw_paths:
        if raw_path.is_file():
            raw_path.unlink()
            removed_raw.add(raw_path)
    for name in JSONL_FILES:
        path = DATA / name
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                records = [json.loads(line) for line in handle if line.strip()]
            with path.open("w", encoding="utf-8") as handle:
                for record in records:
                    if record.get("policy_id") not in POLICY_IDS:
                        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Removed {len(POLICY_IDS)} records and {len(removed_raw)} raw files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
