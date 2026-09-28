"""Fetch original-language policy text from official-source links in OECD.AI's public navigator.

OECD.AI is used only to discover records.  The saved raw file and extracted text are
always from the linked source site, never from OECD's English catalogue description.
"""
from __future__ import annotations

import argparse, csv, hashlib, io, json, re, time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT, RAW = ROOT / "data" / "processed", ROOT / "data" / "raw"
CATALOGUE = "https://api.oecdai.org/policy-initiatives?publishedOnly=true&withoutPagination=true"
HEAD = {"User-Agent": "AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)"}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract(body: bytes, content_type: str) -> str:
    if "pdf" in content_type.lower() or body[:4] == b"%PDF":
        return clean("\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(body)).pages))
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return clean(soup.get_text(" ", strip=True))


def is_block_page(url: str, text: str) -> bool:
    signal = f"{url} {text[:3000]}".lower()
    return any(marker in signal for marker in (
        "validate.perfdrive.com", "shieldsquare", "captcha", "access denied",
        "unusual traffic", "enable javascript to continue", "security check",
    ))


def country(item: dict) -> str:
    return (item.get("gaiinCountry") or {}).get("name") or (item.get("intergovernmentalOrganisation") or {}).get("name") or "International organisation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--pause", type=float, default=.25)
    parser.add_argument("--label", default="", help="Write an isolated batch file for parallel collection")
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    session = requests.Session(); session.headers.update(HEAD)
    catalogue_cache = RAW / "oecd_policy_navigator_catalogue.json"
    if catalogue_cache.exists():
        catalogue = json.loads(catalogue_cache.read_text(encoding="utf-8"))
    else:
        catalogue = session.get(CATALOGUE, timeout=90).json()
        catalogue_cache.write_text(json.dumps(catalogue, ensure_ascii=False), encoding="utf-8")
    items = catalogue[args.offset:args.offset + args.limit]
    rows, failed = [], []
    RAW.mkdir(parents=True, exist_ok=True)
    for pos, item in enumerate(items, args.offset + 1):
        url = item.get("website") or (item.get("relevantUrls") or [None])[0]
        if not url or not url.startswith(("http://", "https://")):
            failed.append({"catalogue_id": item.get("id"), "title_original": item.get("originalName") or item.get("englishName"), "official_url": url or "", "error": "No linked source URL"})
            continue
        try:
            response = session.get(url, timeout=args.timeout, allow_redirects=True, stream=True)
            response.raise_for_status()
            if int(response.headers.get("content-length", "0") or 0) > 15_000_000:
                raise requests.RequestException("Source file exceeds 15 MB extraction safety limit")
            body = response.content
            if len(body) > 15_000_000:
                raise requests.RequestException("Source file exceeds 15 MB extraction safety limit")
            fulltext = extract(body, response.headers.get("content-type", ""))
            if len(fulltext) < 500:
                raise requests.RequestException("No usable original-language source text")
            if is_block_page(response.url, fulltext):
                raise requests.RequestException("Anti-bot or access-denied page, not policy text")
            digest = hashlib.sha256(body).hexdigest()
            suffix = ".pdf" if body[:4] == b"%PDF" else ".html"
            policy_id = f"OECD-LINK-{item['id']}"
            raw = RAW / f"{policy_id}__{digest[:16]}{suffix}"
            raw.write_bytes(body)
            organisations = item.get("responsibleOrganisation") or item.get("responsibleOrganisationSI") or country(item)
            tags = "; ".join(tag.get("name", "") for tag in item.get("tags", []) if tag.get("name"))
            rows.append({
                "policy_id": policy_id,
                "title_original": item.get("originalName") or item.get("englishName", ""),
                "country_or_org": country(item),
                "jurisdiction_level": "supranational" if item.get("intergovernmentalOrganisation") else "national",
                "issuer": organisations,
                "policy_type": (item.get("initiativeType") or {}).get("name") or item.get("category") or "policy initiative",
                "legal_status": item.get("status") or "unknown",
                "published_date": str(item.get("startYear") or item.get("updatedAt", ""))[:10],
                "language": "und",
                "topics": tags,
                "official_url": url,
                "official_url_final": response.url,
                "source_domain": urlparse(response.url).netloc,
                "content_sha256": digest,
                "raw_file": str(raw.relative_to(ROOT)).replace("\\", "/"),
                "fetched_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "fulltext_char_count": len(fulltext),
                "content_extraction_status": "extracted",
                "content_summary_original": fulltext[:500],
                "verification_status": "verified_http",
                "discovery_catalogue": "OECD.AI Policy Navigator",
                "discovery_catalogue_id": item["id"],
            })
            print(f"[{pos}] OK {policy_id} {response.url}")
        except (requests.RequestException, ValueError, OSError) as exc:
            failed.append({"catalogue_id": item.get("id"), "title_original": item.get("originalName") or item.get("englishName"), "official_url": url, "error": clean(str(exc))})
            print(f"[{pos}] FAIL {url}")
        time.sleep(args.pause)
    suffix = f"_{args.label}" if args.label else ""
    for name, records in ((f"oecd_linked_verified{suffix}.csv", rows), (f"oecd_linked_failed{suffix}.csv", failed)):
        path = OUT / name
        if args.append and path.exists():
            with path.open(encoding="utf-8-sig", newline="") as handle:
                existing = list(csv.DictReader(handle))
            seen = {row.get("official_url", "") for row in existing}
            records = existing + [row for row in records if row.get("official_url", "") not in seen]
        fields = list(records[0]) if records else ["catalogue_id", "title_original", "official_url", "error"]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(records)
    print(json.dumps({"catalogue_slice": len(items), "verified": len(rows), "failed": len(failed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
