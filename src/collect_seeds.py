"""Fetch and verify curated, official AI-policy seed records.

This script is intentionally conservative: it only emits records backed by
successful HTTP responses from the official URL listed in config/seed_policies.csv.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
SEED_FILE = ROOT / "config" / "seed_policies.csv"
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"

HEADERS = {
    "User-Agent": "AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)",
    "Accept": "text/html,application/pdf,application/xhtml+xml;q=0.9,*/*;q=0.5",
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def title_from_html(content: bytes) -> str:
    soup = BeautifulSoup(content, "html.parser")
    for selector in ("h1", "meta[property='og:title']", "title"):
        node = soup.select_one(selector)
        if node is None:
            continue
        value = node.get("content", "") if node.name == "meta" else node.get_text(" ", strip=True)
        if clean_text(value):
            return clean_text(value)
    return ""


def text_preview(content: bytes, content_type: str) -> str:
    if "html" not in content_type.lower():
        return ""
    soup = BeautifulSoup(content, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    return clean_text(soup.get_text(" ", strip=True))[:1000]


def suffix_for(content_type: str, url: str) -> str:
    if "pdf" in content_type.lower() or url.lower().split("?", 1)[0].endswith(".pdf"):
        return ".pdf"
    if "json" in content_type.lower():
        return ".json"
    return ".html"


def fetch_record(session: requests.Session, row: dict[str, str], timeout: int) -> dict[str, str]:
    started = datetime.now(UTC).replace(microsecond=0).isoformat()
    response = session.get(row["official_url"], timeout=timeout, allow_redirects=True)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    body = response.content
    preview = text_preview(body, content_type)
    if "html" in content_type.lower() and len(preview) < 120:
        raise requests.RequestException("Response did not contain usable policy text (possible access-control page)")
    digest = hashlib.sha256(body).hexdigest()
    raw_name = f"{row['policy_id']}__{digest[:16]}{suffix_for(content_type, response.url)}"
    raw_path = RAW_DIR / raw_name
    raw_path.write_bytes(body)

    return {
        **row,
        "official_url_final": response.url,
        "source_domain": urlparse(response.url).netloc.lower(),
        "http_status": str(response.status_code),
        "content_type": content_type,
        "raw_file": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
        "content_sha256": digest,
        "fetched_at_utc": started,
        "page_title_detected": title_from_html(body) if "html" in content_type.lower() else "",
        "text_preview": preview,
        "verification_status": "verified_http",
        "collection_error": "",
    }


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--pause", type=float, default=0.8, help="Seconds between requests")
    parser.add_argument("--limit", type=int, default=0, help="Optional number of seed rows")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with SEED_FILE.open(encoding="utf-8-sig", newline="") as handle:
        seeds = list(csv.DictReader(handle))
    if args.limit:
        seeds = seeds[: args.limit]

    session = requests.Session()
    session.headers.update(HEADERS)
    successful: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []

    for index, row in enumerate(seeds, start=1):
        try:
            collected = fetch_record(session, row, args.timeout)
            successful.append(collected)
            print(f"[{index}/{len(seeds)}] OK   {row['policy_id']} {collected['http_status']}")
        except requests.RequestException as exc:
            failed.append({
                **row,
                "fetched_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "verification_status": "fetch_failed",
                "collection_error": clean_text(str(exc)),
            })
            print(f"[{index}/{len(seeds)}] FAIL {row['policy_id']} {exc}")
        if index < len(seeds):
            time.sleep(args.pause)

    base_fields = list(seeds[0].keys()) if seeds else []
    policy_fields = base_fields + [
        "official_url_final", "source_domain", "http_status", "content_type", "raw_file",
        "content_sha256", "fetched_at_utc", "page_title_detected", "text_preview",
        "verification_status", "collection_error",
    ]
    write_csv(OUT_DIR / "policies.csv", successful, policy_fields)
    write_csv(OUT_DIR / "failed_fetches.csv", failed, base_fields + ["fetched_at_utc", "verification_status", "collection_error"])
    summary = {
        "run_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "seed_rows": len(seeds),
        "verified_records": len(successful),
        "failed_records": len(failed),
        "countries_or_organisations": sorted({row["country_or_org"] for row in successful}),
    }
    (OUT_DIR / "collection_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
