"""Print a compact coverage and quality summary for the master dataset."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"


def read_rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    master = read_rows("ai_policies_master.csv")
    candidates = read_rows("policy_candidates.csv")
    failed_seed = read_rows("failed_fetches.csv")
    held = read_rows("master_excluded_incomplete.csv")
    enriched = read_rows("ai_policies_enriched.csv") if (OUT / "ai_policies_enriched.csv").exists() else []
    report = {
        "master_records": len(master),
        "jurisdictions_or_organisations": dict(sorted(Counter(row["country_or_org"] for row in master).items())),
        "jurisdiction_levels": dict(sorted(Counter(row["jurisdiction_level"] for row in master).items())),
        "policy_types": dict(sorted(Counter(row["policy_type"] for row in master).items())),
        "pending_candidates": len(candidates),
        "seed_fetch_failures": len(failed_seed),
        "held_for_metadata_completion": len(held),
        "content_extracted_records": sum(row["content_extraction_status"] == "extracted" for row in enriched),
        "content_extraction_failures": sum(row["content_extraction_status"] != "extracted" for row in enriched),
    }
    target = OUT / "status_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
