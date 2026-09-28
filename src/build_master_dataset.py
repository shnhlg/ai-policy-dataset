"""Merge verified collections into one de-duplicated master policy table."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "processed"
SOURCES = [OUT_DIR / "policies.csv", OUT_DIR / "beijing_policies.csv", *sorted(OUT_DIR.glob("govuk_verified*.csv")), *sorted(OUT_DIR.glob("federal_register_verified*.csv")), *sorted(OUT_DIR.glob("regulations_gov_verified*.csv")), *sorted(OUT_DIR.glob("oecd_linked_verified*.csv")), *sorted(OUT_DIR.glob("shanghai_ai_verified*.csv")), *sorted(OUT_DIR.glob("eurlex_ai_verified*.csv"))]
OUT = OUT_DIR / "ai_policies_master.csv"
INCOMPLETE_OUT = OUT_DIR / "master_excluded_incomplete.csv"


def normalise(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value or "", flags=re.UNICODE).lower()


def main() -> int:
    all_rows: list[dict[str, str]] = []
    fields: list[str] = []
    for path in SOURCES:
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields.extend(field for field in reader.fieldnames or [] if field != "title_zh" and field not in fields)
            all_rows.extend(reader)
    seen: set[tuple[str, ...]] = set()
    used_policy_ids: set[str] = set()
    master: list[dict[str, str]] = []
    incomplete: list[dict[str, str]] = []
    for row in all_rows:
        required = ("title_original", "country_or_org", "issuer", "published_date", "official_url", "content_sha256", "raw_file")
        if any(not row.get(field, "").strip() for field in required):
            incomplete.append(row)
            continue
        exact_key = ("content", row.get("content_sha256", ""))
        identity_key = (
            "identity",
            normalise(row.get("title_original", "")),
            normalise(row.get("issuer", "")),
            row.get("published_date", ""),
        )
        if exact_key in seen or identity_key in seen:
            continue
        seen.add(exact_key)
        seen.add(identity_key)
        # Some paginated source APIs reorder results between runs.  Their legacy
        # page/position IDs can then collide even though the official URL and raw
        # file are distinct.  Keep both source documents with an unambiguous ID.
        base_id = row.get("policy_id", "")
        if base_id in used_policy_ids:
            suffix = 2
            while f"{base_id}-D{suffix}" in used_policy_ids:
                suffix += 1
            row = dict(row)
            row["policy_id"] = f"{base_id}-D{suffix}"
        used_policy_ids.add(row.get("policy_id", ""))
        master.append(row)
    with OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(master)
    with INCOMPLETE_OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(incomplete)
    print(f"Master dataset: {len(master)} complete records from {len(all_rows)} verified collection rows; {len(incomplete)} held for metadata completion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
