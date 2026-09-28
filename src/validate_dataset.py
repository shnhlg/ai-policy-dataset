"""Basic quality gates for the verified AI-policy seed dataset."""

from __future__ import annotations

import csv
import sys
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "processed" / "ai_policies_master.csv"
REQUIRED = {
    "policy_id", "title_original", "country_or_org", "issuer", "policy_type",
    "published_date", "official_url", "official_url_final", "verification_status",
    "content_sha256", "raw_file",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DATASET, help="CSV file to validate")
    args = parser.parse_args()
    dataset = args.file if args.file.is_absolute() else ROOT / args.file
    if not dataset.exists():
        print("Dataset missing. Run src/collect_seeds.py first.", file=sys.stderr)
        return 2
    with dataset.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print("Dataset contains no verified rows.", file=sys.stderr)
        return 1
    missing_columns = REQUIRED - set(rows[0])
    if missing_columns:
        print(f"Missing columns: {sorted(missing_columns)}", file=sys.stderr)
        return 1
    ids = [row["policy_id"] for row in rows]
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    missing_values = [
        (row["policy_id"], field)
        for row in rows
        for field in REQUIRED
        if not row.get(field, "").strip()
    ]
    non_verified = [row["policy_id"] for row in rows if row["verification_status"] != "verified_http"]
    missing_raw = [row["policy_id"] for row in rows if not (ROOT / row["raw_file"]).exists()]
    if duplicate_ids or missing_values or non_verified or missing_raw:
        print(f"duplicate_ids={duplicate_ids}")
        print(f"missing_values={missing_values[:20]}")
        print(f"non_verified={non_verified}")
        print(f"missing_raw={missing_raw}")
        return 1
    print(f"PASS: {len(rows)} verified records; {len(set(row['country_or_org'] for row in rows))} jurisdictions/organisations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
