"""Harvest official EU AI-topic documents through the Publications Office CELLAR API.

The source is the official EuroVoc ``artificial intelligence`` descriptor (3030).
Only English originals are downloaded so each record represents one policy/publication,
not its parallel language editions.  Files and metadata come directly from the
Publications Office's public SPARQL/REST interfaces.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import io
import requests
from PyPDF2 import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
HEAD = {"User-Agent": "AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)"}

QUERY = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?work ?title ?date ?item ?format WHERE {
  { ?work cdm:work_is_about_concept_eurovoc <http://eurovoc.europa.eu/3030> }
  UNION
  { ?work cdm:publication_general_is_about_concept_eurovoc <http://eurovoc.europa.eu/3030> }
  OPTIONAL { ?work cdm:work_date_document ?date }
  ?expr cdm:expression_belongs_to_work ?work ;
        cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
        cdm:expression_title ?title .
  ?manif cdm:manifestation_manifests_expression ?expr ;
         cdm:manifestation_type ?format .
  ?item cdm:item_belongs_to_manifestation ?manif .
  FILTER(CONTAINS(LCASE(STR(?format)), "pdf"))
}"""

QUERY_ALL_LANGUAGES = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX purl: <http://purl.org/dc/elements/1.1/>
SELECT DISTINCT ?work ?title ?date ?item ?format ?langCode WHERE {
  { ?work cdm:work_is_about_concept_eurovoc <http://eurovoc.europa.eu/3030> }
  UNION
  { ?work cdm:publication_general_is_about_concept_eurovoc <http://eurovoc.europa.eu/3030> }
  OPTIONAL { ?work cdm:work_date_document ?date }
  ?expr cdm:expression_belongs_to_work ?work ;
        cdm:expression_uses_language ?lang ; cdm:expression_title ?title .
  ?lang purl:identifier ?langCode .
  ?manif cdm:manifestation_manifests_expression ?expr ;
         cdm:manifestation_type ?format .
  ?item cdm:item_belongs_to_manifestation ?manif .
  FILTER(CONTAINS(LCASE(STR(?format)), "pdf"))
}"""


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def bindings(all_languages: bool = False) -> list[dict[str, str]]:
    response = requests.get(
        SPARQL,
        params={"query": QUERY_ALL_LANGUAGES if all_languages else QUERY, "format": "json"},
        headers={**HEAD, "Accept": "application/sparql-results+json"},
        timeout=120,
    )
    response.raise_for_status()
    candidates: dict[str, dict[str, str]] = {}
    # A document can expose PDF, PDF/A and PDF/X manifestations.  Keep its first
    # stream: this prevents parallel technical variants becoming fake policies.
    for binding in response.json()["results"]["bindings"]:
        work = binding["work"]["value"]
        lang = binding.get("langCode", {}).get("value", "ENG")
        key = f"{work}|{lang}"
        if key not in candidates:
            candidates[key] = {
                "work": work,
                "title": binding["title"]["value"],
                "date": binding.get("date", {}).get("value", "")[:10],
                "item": binding["item"]["value"],
                "lang": lang.lower(),
            }
    return list(candidates.values())


def fetch(index: int, candidate: dict[str, str], timeout: int, resume: bool) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    try:
        policy_id = f"EU-CELLAR-AI-{candidate.get('lang', 'eng').upper()}-{index:05d}"
        prior = next(RAW.glob(f"{policy_id}__*.pdf"), None) if resume else None
        final_url = candidate["item"]
        cached = prior is not None
        if prior:
            body = prior.read_bytes()
        else:
            session = requests.Session()
            session.headers.update(HEAD)
            response = session.get(candidate["item"], timeout=timeout, stream=True, allow_redirects=True)
            response.raise_for_status()
            length = int(response.headers.get("content-length", "0") or 0)
            if length > 25_000_000:
                raise requests.RequestException("Source file exceeds 25 MB extraction safety limit")
            body = response.content
            final_url = response.url
        if len(body) > 25_000_000 or not body.startswith(b"%PDF"):
            raise requests.RequestException("No usable official PDF")
        # Files found by --resume have already passed this collector's text gate
        # in an earlier run.  Avoid re-parsing large PDFs; final enrichment still
        # extracts and records their complete bodies independently.
        fulltext = "" if cached else clean("\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(body)).pages))
        if not cached and len(fulltext) < 300:
            raise requests.RequestException("No usable policy text")
        digest = hashlib.sha256(body).hexdigest()
        raw = RAW / f"{policy_id}__{digest[:16]}.pdf"
        if not prior:
            raw.write_bytes(body)
        return ({
            "policy_id": policy_id,
            "title_original": candidate["title"],
            "country_or_org": "European Union",
            "jurisdiction_level": "supranational",
            "issuer": "Publications Office of the European Union",
            "policy_type": "official publication",
            "legal_status": "unknown",
            "published_date": candidate["date"] or "1900-01-01",
            "language": candidate.get("lang", "en"),
            "topics": "artificial intelligence (EuroVoc 3030)",
            "official_url": candidate["work"],
            "official_url_final": final_url,
            "source_domain": urlparse(final_url).netloc,
            "content_sha256": digest,
            "raw_file": str(raw.relative_to(ROOT)).replace("\\", "/"),
            "fetched_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "fulltext_char_count": len(fulltext),
            "content_extraction_status": "cached_verified" if cached else "extracted",
            "content_summary_original": fulltext[:500],
            "verification_status": "verified_http",
        }, None)
    except Exception as exc:  # retain failed official candidates for reproducibility
        return None, {"title_original": candidate["title"], "official_url": candidate["work"], "error": clean(str(exc))}


def write_csv(path: Path, rows: list[dict[str, str]], fallback: list[str]) -> None:
    fields = list(rows[0]) if rows else fallback
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 means all candidates")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=6)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--all-languages", action="store_true", help="retain each official EU language expression as its own original-text record")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    candidates = bindings(args.all_languages)
    if args.limit:
        candidates = candidates[:args.limit]
    rows: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(fetch, i, candidate, args.timeout, args.resume) for i, candidate in enumerate(candidates, 1)]
        for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row, failure = future.result()
            if row:
                rows.append(row)
            if failure:
                failures.append(failure)
            if done % 25 == 0 or done == len(candidates):
                print(f"[{done}/{len(candidates)}] verified={len(rows)} failed={len(failures)}", flush=True)
            time.sleep(0.02)
    rows.sort(key=lambda row: row["policy_id"])
    write_csv(OUT / "eurlex_ai_verified.csv", rows, ["policy_id", "title_original", "official_url"])
    write_csv(OUT / "eurlex_ai_failed.csv", failures, ["title_original", "official_url", "error"])
    print(json.dumps({"candidates": len(candidates), "verified": len(rows), "failed": len(failures)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
