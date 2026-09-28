"""Merge successful failed-only retries into the canonical content datasets."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    master_fields, master_rows = read_csv(DATA / "ai_policies_master.csv")
    content_fields, content_rows = read_csv(DATA / "ai_policies_content_master.csv")
    _, retry_success = read_csv(DATA / "content_extraction_retry_success.csv")
    _, retry_failures = read_csv(DATA / "content_extraction_retry_failures.csv")
    by_id = {row["policy_id"]: row for row in content_rows}
    by_id.update({row["policy_id"]: row for row in retry_success})
    remaining_failures = {row["policy_id"]: row for row in retry_failures}
    merged_success = [by_id[row["policy_id"]] for row in master_rows if row["policy_id"] in by_id]
    merged_failures = [remaining_failures[row["policy_id"]] for row in master_rows if row["policy_id"] in remaining_failures]
    all_rows = [by_id.get(row["policy_id"], remaining_failures.get(row["policy_id"], row)) for row in master_rows]
    write_csv(DATA / "ai_policies_content_master.csv", content_fields, merged_success)
    write_csv(DATA / "content_extraction_failures.csv", content_fields, merged_failures)
    write_csv(DATA / "ai_policies_enriched.csv", content_fields, all_rows)

    details: dict[str, dict] = {}
    for path in (DATA / "policy_fulltexts.jsonl", DATA / "policy_fulltexts_retry.jsonl"):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                details[record["policy_id"]] = record
    with (DATA / "policy_fulltexts.jsonl").open("w", encoding="utf-8") as handle:
        for row in master_rows:
            record = details.get(row["policy_id"])
            if record:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Merged content: {len(merged_success)} extracted, {len(merged_failures)} failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
