"""Export OECD.AI's maintained Policy Navigator catalogue as a standalone curated library."""
from __future__ import annotations

import csv, json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "oecd_policy_navigator_catalogue.json"
OUT = ROOT / "data" / "curated" / "oecd_ai_policy_navigator"


def value(item: dict, key: str) -> str:
    thing = item.get(key)
    if isinstance(thing, dict):
        return str(thing.get("name") or thing.get("title") or "")
    return str(thing or "")


def country(item: dict) -> str:
    return value(item, "gaiinCountry") or value(item, "intergovernmentalOrganisation") or "International organisation"


def main() -> None:
    items = json.loads(RAW.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in items:
        rows.append({
            "oecd_catalogue_id": item.get("id", ""),
            "title_original": item.get("originalName") or item.get("englishName") or "",
            "title_english_catalogue": item.get("englishName") or "",
            "country_or_org": country(item),
            "responsible_organisation": value(item, "responsibleOrganisation") or value(item, "responsibleOrganisationSI"),
            "initiative_type": value(item, "initiativeType") or str(item.get("category") or ""),
            "status": str(item.get("status") or ""),
            "start_year": str(item.get("startYear") or ""),
            "end_year": str(item.get("endYear") or ""),
            "website": item.get("website") or "",
            "relevant_urls": "; ".join(item.get("relevantUrls") or []),
            "tags": "; ".join(tag.get("name", "") for tag in item.get("tags") or [] if isinstance(tag, dict)),
            "catalogue_updated_at": str(item.get("updatedAt") or ""),
            "catalogue_source": "OECD.AI Policy Navigator",
            "exported_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        })
    with (OUT / "oecd_ai_policy_navigator_curated.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else []); writer.writeheader(); writer.writerows(rows)
    with (OUT / "oecd_ai_policy_navigator_curated.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    (OUT / "README.md").write_text("# OECD.AI 人工维护精选库\n\n本目录保存 OECD.AI Policy Navigator 的完整目录导出。它是人工维护的政策倡议精选库；不等同于官方原文文件库。`oecd_catalogue_id` 可与原始目录及外部官方来源关联。\n", encoding="utf-8")
    print(f"OECD curated library: {len(rows)} catalogue initiatives")


if __name__ == "__main__":
    main()
