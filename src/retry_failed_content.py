"""Retry only previously failed policy-body extractions without overwriting successes."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import enrich_policy_content as extractor


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
FAILURES = DATA_DIR / "content_extraction_failures.csv"
RETRY_SUCCESS = DATA_DIR / "content_extraction_retry_success.csv"
RETRY_FAILURES = DATA_DIR / "content_extraction_retry_failures.csv"
RETRY_FULLTEXT = DATA_DIR / "policy_fulltexts_retry.jsonl"


def make_output(row: dict[str, str], text: str, parser: str, status: str, error: str) -> dict[str, str]:
    excerpts = {field: "" for field in extractor.RULES}
    sector_mapping: dict[str, list[str]] = {}
    technology_mapping: dict[str, list[str]] = {}
    if status == "extracted":
        source_sentences = extractor.sentences(text)
        excerpts = {
            field: extractor.choose_excerpts(source_sentences, keywords)
            for field, keywords in extractor.RULES.items()
        }
        sector_mapping = {
            "education": ["education", "school"], "health": ["health", "medical"],
            "manufacturing": ["manufacturing", "industry"], "public_sector": ["government", "agency", "public sector"],
            "media": ["content", "media"], "security": ["defence", "defense", "security"],
        }
        technology_mapping = {
            "generative_ai": ["generative"], "foundation_models": ["foundation model", "large language model"],
            "recommendation": ["recommendation algorithm"], "deep_synthesis": ["deep synthesis", "deepfake"],
            "risk_management": ["risk management"], "automated_decision": ["automated decision"],
        }
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
    return {
        **row,
        "content_summary_original": extractor.summary_original(row, excerpts["policy_objectives"], excerpts["policy_measures"]),
        "policy_objectives": excerpts["policy_objectives"], "policy_measures": excerpts["policy_measures"],
        "regulatory_requirements": excerpts["regulatory_requirements"], "target_entities": excerpts["target_entities"],
        "sectors_extracted": extractor.labels_from_text(text, sector_mapping),
        "technologies_extracted": extractor.labels_from_text(text, technology_mapping),
        "fulltext_record_id": row["policy_id"], "fulltext_sha256": text_hash,
        "fulltext_char_count": str(len(text)), "content_extraction_status": status,
        "content_extraction_error": error,
    }


def main() -> int:
    extractor.MAX_PDF_BYTES = None
    extractor.MAX_PDF_PAGES = None
    with FAILURES.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print("Retry: no failed records to process.")
        return 0
    fieldnames = list(rows[0])
    additions = [
        "content_summary_original", "policy_objectives", "policy_measures", "regulatory_requirements", "target_entities",
        "sectors_extracted", "technologies_extracted", "fulltext_record_id", "fulltext_sha256", "fulltext_char_count",
        "content_extraction_status", "content_extraction_error",
    ]
    fieldnames += [field for field in additions if field not in fieldnames]
    successful = 0
    with RETRY_SUCCESS.open("w", encoding="utf-8-sig", newline="") as success_handle, \
            RETRY_FAILURES.open("w", encoding="utf-8-sig", newline="") as failure_handle, \
            RETRY_FULLTEXT.open("w", encoding="utf-8") as fulltext_handle:
        success_writer = csv.DictWriter(success_handle, fieldnames=fieldnames)
        failure_writer = csv.DictWriter(failure_handle, fieldnames=fieldnames)
        success_writer.writeheader()
        failure_writer.writeheader()
        for index, row in enumerate(rows, start=1):
            try:
                text, parser = extractor.extract_text(ROOT / row["raw_file"])
                if not text:
                    raise ValueError("no extractable text")
                status, error = "extracted", ""
            except Exception as exc:
                text, parser, status, error = "", "", "extraction_failed", extractor.clean(str(exc))
            output = make_output(row, text, parser, status, error)
            (success_writer if status == "extracted" else failure_writer).writerow(output)
            fulltext_handle.write(json.dumps({
                "policy_id": row["policy_id"], "fulltext": text,
                "fulltext_sha256": output["fulltext_sha256"], "fulltext_char_count": len(text),
                "extraction_parser": parser, "content_extraction_status": status,
                "content_extraction_error": error,
            }, ensure_ascii=False) + "\n")
            successful += status == "extracted"
            if index % 10 == 0:
                for handle in (success_handle, failure_handle, fulltext_handle):
                    handle.flush()
                print(f"Retry progress: {index}/{len(rows)} ({successful} extracted).", flush=True)
    print(f"Retry completed: {successful}/{len(rows)} records extracted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
