"""Verify and ingest policy candidates from Beijing's official AI policy index."""

from __future__ import annotations

import csv
import hashlib
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data" / "processed" / "policy_candidates.csv"
SEED_POLICIES = ROOT / "data" / "processed" / "policies.csv"
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
HEADERS = {"User-Agent": "AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)"}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def field_after(text: str, label: str, next_label: str) -> str:
    pattern = re.escape(label) + r"\s*(.*?)\s*" + re.escape(next_label)
    match = re.search(pattern, text)
    return clean(match.group(1)) if match else ""


def classify_type(title: str) -> str:
    for token, label in (("办法", "管理办法"), ("指南", "指南"), ("纲要", "纲要"), ("措施", "政策措施"), ("意见", "政策意见"), ("方案", "实施方案"), ("计划", "行动计划")):
        if token in title:
            return label
    return "政策文件"


def classify_topics(title: str) -> str:
    topics = ["地方政策", "AI应用"]
    mapping = {"教育": "教育", "医疗": "医疗健康", "医药": "医疗健康", "工业": "工业", "科学研究": "科研", "芯片": "芯片", "视听": "文化传媒", "通用": "通用人工智能", "职业": "人才"}
    for token, label in mapping.items():
        if token in title and label not in topics:
            topics.append(label)
    return ";".join(topics)


def parse_html(body: bytes) -> tuple[str, str, str, str, str]:
    soup = BeautifulSoup(body, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    text = clean(soup.get_text(" ", strip=True))
    issuer = field_after(text, "[发文机构]", "[联合发文单位]")
    published_date = field_after(text, "[发布日期]", "[有效性]")
    effective = field_after(text, "[有效性]", "[文件来源]")
    title_node = soup.select_one("h1") or soup.select_one("title")
    detected_title = clean(title_node.get_text(" ", strip=True)) if title_node else ""
    return issuer, published_date, effective, detected_title, text[:1000]


def main() -> int:
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as handle:
        candidates = [row for row in csv.DictReader(handle) if row["source_id"] == "CN-BJ-001"]
    with SEED_POLICIES.open(encoding="utf-8-sig", newline="") as handle:
        existing_urls = {row["official_url"] for row in csv.DictReader(handle)}
    candidates = [row for row in candidates if row["official_url"] not in existing_urls]
    session = requests.Session()
    session.headers.update(HEADERS)
    successes: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []

    for index, candidate in enumerate(candidates, start=1):
        try:
            response = session.get(candidate["official_url"], timeout=30)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                raise requests.RequestException(f"Expected HTML, received {content_type}")
            body = response.content
            digest = hashlib.sha256(body).hexdigest()
            policy_id = f"CN-BJ-{index:05d}"
            raw_path = RAW_DIR / f"{policy_id}__{digest[:16]}.html"
            raw_path.write_bytes(body)
            issuer, published_date, effective, detected_title, preview = parse_html(body)
            published_match = re.search(r"\d{4}-\d{2}-\d{2}", published_date)
            title = candidate["title_original"]
            successes.append({
                "policy_id": policy_id,
                "title_original": title,
                "title_zh": title,
                "country_or_org": "中国",
                "jurisdiction_level": "subnational",
                "issuer": issuer or "北京市有关部门",
                "policy_type": classify_type(title),
                "legal_status": "现行" if effective in {"是", "有效"} else "待核验",
                "published_date": published_match.group(0) if published_match else "",
                "language": "zh",
                "topics": classify_topics(title),
                "official_url": candidate["official_url"],
                "official_url_final": response.url,
                "source_domain": urlparse(response.url).netloc.lower(),
                "http_status": str(response.status_code),
                "content_type": content_type,
                "raw_file": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
                "content_sha256": digest,
                "fetched_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "page_title_detected": detected_title,
                "text_preview": preview,
                "verification_status": "verified_http",
                "collection_error": "",
                "candidate_id": candidate["candidate_id"],
                "review_status": "rule_reviewed",
            })
            print(f"[{index}/{len(candidates)}] OK   {policy_id}")
        except requests.RequestException as exc:
            failures.append({**candidate, "collection_error": clean(str(exc))})
            print(f"[{index}/{len(candidates)}] FAIL {candidate['candidate_id']} {exc}")
        if index < len(candidates):
            time.sleep(0.6)

    fields = list(successes[0]) if successes else []
    with (OUT_DIR / "beijing_policies.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(successes)
    failure_fields = list(failures[0]) if failures else ["candidate_id", "collection_error"]
    with (OUT_DIR / "beijing_failed_fetches.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=failure_fields)
        writer.writeheader()
        writer.writerows(failures)
    print(f"Ingested {len(successes)} Beijing policies; {len(failures)} fetch failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
