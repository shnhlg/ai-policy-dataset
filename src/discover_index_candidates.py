"""Discover policy candidates from registered official index pages.

Discovery is kept separate from formal ingestion: candidates require a
policy-type and metadata review before they may enter policies.csv.
"""

from __future__ import annotations

import csv
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "config" / "index_sources.csv"
OUTPUT = ROOT / "data" / "processed" / "policy_candidates.csv"
HEADERS = {"User-Agent": "AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)"}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def main() -> int:
    with INDEX_FILE.open(encoding="utf-8-sig", newline="") as handle:
        indexes = list(csv.DictReader(handle))
    rows: list[dict[str, str]] = []
    session = requests.Session()
    session.headers.update(HEADERS)

    for source in indexes:
        response = session.get(source["entry_url"], timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        include = [term for term in source["keywords"].split("|") if term]
        exclude = [term for term in source["exclude_keywords"].split("|") if term]
        for link in soup.select("a[href]"):
            title = clean(link.get_text(" ", strip=True))
            if not title or not any(term in title for term in include):
                continue
            if any(term in title for term in exclude):
                continue
            official_url = urljoin(response.url, link["href"])
            if urlparse(official_url).scheme not in {"http", "https"}:
                continue
            fingerprint = hashlib.sha256(f"{source['source_id']}|{official_url}".encode()).hexdigest()[:12]
            rows.append({
                "candidate_id": f"CAND-{fingerprint}",
                "source_id": source["source_id"],
                "source_name": source["source_name"],
                "jurisdiction": source["jurisdiction"],
                "title_original": title,
                "official_url": official_url,
                "found_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "review_status": "pending",
                "review_note": "Discovered from official policy index; verify type, issuer, date and legal status before ingestion.",
            })

    unique = {row["official_url"]: row for row in rows}
    fields = list(rows[0]) if rows else ["candidate_id", "source_id", "source_name", "jurisdiction", "title_original", "official_url", "found_at_utc", "review_status", "review_note"]
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(unique.values(), key=lambda item: item["title_original"]))
    print(f"Discovered {len(unique)} unique candidates from {len(indexes)} official indexes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
