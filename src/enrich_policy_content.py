"""Extract full text and structured policy-content fields from cached sources.

The extractor is evidence-first.  It stores the full source text separately and
puts only short, source-language excerpts in the tabular policy dataset.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path

from bs4 import BeautifulSoup
from PyPDF2 import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
MASTER = DATA_DIR / "ai_policies_master.csv"
ENRICHED = DATA_DIR / "ai_policies_enriched.csv"
CONTENT_MASTER = DATA_DIR / "ai_policies_content_master.csv"
CONTENT_FAILURES = DATA_DIR / "content_extraction_failures.csv"
FULLTEXT = DATA_DIR / "policy_fulltexts.jsonl"

MAX_EXCERPT_CHARS = 900
MAX_PDF_BYTES: int | None = 1_000_000
MAX_PDF_PAGES: int | None = 50

RULES = OrderedDict({
    "policy_objectives": [
        "目标", "目的", "旨在", "到20", "推动", "促进", "提升", "保障",
        "objective", "purpose", "aim", "will", "ensure", "promote",
    ],
    "policy_measures": [
        "支持", "建立", "建设", "开展", "鼓励", "加快", "制定", "加强", "实施",
        "provide", "establish", "develop", "support", "implement", "create", "fund",
    ],
    "regulatory_requirements": [
        "应当", "不得", "禁止", "备案", "评估", "审查", "报告", "责任", "处罚",
        "shall", "must", "prohibit", "require", "obligation", "compliance", "risk management",
    ],
    "target_entities": [
        "服务提供者", "使用者", "企业", "机构", "部门", "学校", "平台", "开发者", "部署者",
        "provider", "developer", "deployer", "agency", "organisation", "organization", "business", "operator",
    ],
})


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_html(path: Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    return clean(soup.get_text(" ", strip=True))


def extract_pdf(path: Path) -> str:
    if MAX_PDF_BYTES is not None and path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds {MAX_PDF_BYTES} byte extraction safety limit")
    reader = PdfReader(str(path))
    pages = reader.pages if MAX_PDF_PAGES is None else reader.pages[:MAX_PDF_PAGES]
    return clean("\n".join(page.extract_text() or "" for page in pages))


def extract_text(path: Path) -> tuple[str, str]:
    if MAX_PDF_BYTES is not None and path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError(f"source exceeds {MAX_PDF_BYTES} byte extraction safety limit")
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return extract_html(path), "html"
    if suffix == ".pdf":
        return extract_pdf(path), "pdf"
    return "", "unsupported"


def sentences(text: str) -> list[str]:
    text = re.sub(r"(?=(?:第[一二三四五六七八九十百千万0-9]+条|[一二三四五六七八九十]+、|（[一二三四五六七八九十0-9]+）))", "\n", text)
    chunks = re.split(r"\n+|(?<=[。！？；!?;])|(?<=[.])\s+(?=[A-Z])", text)
    result: list[str] = []
    for chunk in chunks:
        item = clean(chunk)
        if len(item) >= 35 and item not in result:
            result.append(item)
    return result


def choose_excerpts(source_sentences: list[str], keywords: list[str], limit: int = 3) -> str:
    selected: list[str] = []
    for sentence in source_sentences:
        lowercase = sentence.lower()
        if any(keyword.lower() in lowercase for keyword in keywords):
            selected.append(sentence)
        if len(selected) >= limit:
            break
    output = " ".join(selected)
    return output[:MAX_EXCERPT_CHARS]


def labels_from_text(text: str, mapping: dict[str, list[str]]) -> str:
    present: list[str] = []
    lowered = text.lower()
    for label, terms in mapping.items():
        if any(term.lower() in lowered for term in terms):
            present.append(label)
    return ";".join(present)


def summary_original(row: dict[str, str], objectives: str, measures: str) -> str:
    evidence = objectives or measures
    if evidence:
        return evidence[:500]
    return row["title_original"]


def main() -> int:
    with MASTER.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print("Content enrichment: 0/0 records extracted.")
        return 0
    fieldnames = list(rows[0]) + [
        "content_summary_original", "policy_objectives", "policy_measures",
        "regulatory_requirements", "target_entities", "sectors_extracted",
        "technologies_extracted", "fulltext_record_id", "fulltext_sha256",
        "fulltext_char_count", "content_extraction_status", "content_extraction_error",
    ]
    successful = 0
    with ENRICHED.open("w", encoding="utf-8-sig", newline="") as enriched_handle, \
            CONTENT_MASTER.open("w", encoding="utf-8-sig", newline="") as content_handle, \
            CONTENT_FAILURES.open("w", encoding="utf-8-sig", newline="") as failures_handle, \
            FULLTEXT.open("w", encoding="utf-8") as fulltext_handle:
        enriched_writer = csv.DictWriter(enriched_handle, fieldnames=fieldnames)
        content_writer = csv.DictWriter(content_handle, fieldnames=fieldnames)
        failures_writer = csv.DictWriter(failures_handle, fieldnames=fieldnames)
        for writer in (enriched_writer, content_writer, failures_writer):
            writer.writeheader()
        for index, row in enumerate(rows, start=1):
            raw_path = ROOT / row["raw_file"]
            try:
                text, parser = extract_text(raw_path)
                if not text:
                    raise ValueError("no extractable text")
                source_sentences = sentences(text)
                excerpts = {field: choose_excerpts(source_sentences, keywords) for field, keywords in RULES.items()}
                sector_mapping = {
                "教育": ["教育", "学校", "education", "school"],
                "医疗健康": ["医疗", "健康", "医药", "health", "medical"],
                "工业制造": ["工业", "制造", "manufacturing", "industry"],
                "公共治理": ["政府", "公共", "agency", "public sector"],
                "文化传媒": ["视听", "媒体", "content", "media"],
                "国防安全": ["国防", "安全", "defence", "defense", "security"],
            }
                technology_mapping = {
                "生成式AI": ["生成式", "generative"],
                "大模型": ["大模型", "foundation model", "large language model"],
                "算法推荐": ["算法推荐", "recommendation algorithm"],
                "深度合成": ["深度合成", "deep synthesis", "deepfake"],
                "风险管理": ["风险管理", "risk management"],
                "自动化决策": ["自动化决策", "automated decision"],
            }
                status = "extracted"
                error = ""
            except Exception as exc:  # Per-record extraction errors must not halt the batch.
                text, parser = "", ""
                excerpts = {field: "" for field in RULES}
                sector_mapping, technology_mapping = {}, {}
                status = "extraction_failed"
                error = clean(str(exc))
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
            detail = {
                "policy_id": row["policy_id"], "fulltext": text,
                "fulltext_sha256": text_hash, "fulltext_char_count": len(text),
                "extraction_parser": parser, "content_extraction_status": status,
                "content_extraction_error": error,
            }
            output = {
                **row,
                "content_summary_original": summary_original(row, excerpts["policy_objectives"], excerpts["policy_measures"]),
                "policy_objectives": excerpts["policy_objectives"],
                "policy_measures": excerpts["policy_measures"],
                "regulatory_requirements": excerpts["regulatory_requirements"],
                "target_entities": excerpts["target_entities"],
                "sectors_extracted": labels_from_text(text, sector_mapping),
                "technologies_extracted": labels_from_text(text, technology_mapping),
                "fulltext_record_id": row["policy_id"], "fulltext_sha256": text_hash,
                "fulltext_char_count": str(len(text)), "content_extraction_status": status,
                "content_extraction_error": error,
            }
            enriched_writer.writerow(output)
            (content_writer if status == "extracted" else failures_writer).writerow(output)
            fulltext_handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
            if status == "extracted":
                successful += 1
            if index % 100 == 0:
                for handle in (enriched_handle, content_handle, failures_handle, fulltext_handle):
                    handle.flush()
                print(f"Progress: {index}/{len(rows)} ({successful} extracted).", flush=True)
    print(f"Content enrichment: {successful}/{len(rows)} records extracted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
