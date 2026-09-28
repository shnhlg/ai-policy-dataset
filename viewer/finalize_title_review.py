"""Produce the auditable final QA table for contextual title translations."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEWS = Path(__file__).resolve().parent / "contextual_title_reviews.jsonl"
OUTPUT = ROOT / "data" / "processed" / "title_translation_review_2674.csv"
VERSION = "2026-07-external-contextual-v2"
BAD_TERMS = ("人工智能收养", "人工情报", "人造情报", "大赦国际")


def final_status(original: str, translated: str) -> tuple[str, str]:
    source = original.strip()
    if source in {"", "-", "--", "-1"}:
        return "原标题缺失", "源数据没有可翻译的有效标题，保留原值且不编造译名"
    if any(term in translated for term in BAD_TERMS):
        return "需再审", "命中禁用误译词"
    if not re.search(r"[\u4e00-\u9fff]", translated):
        if source == translated.strip() and len(source) <= 30:
            return "专名/缩写保留", "短项目名、品牌名或缩写没有可靠中文全称，保留原文"
        return "需再审", "译文缺少中文且不符合专名保留条件"
    if len(translated) > max(160, len(original) * 5):
        return "需再审", "译文长度异常"
    return "AI上下文译审通过", "已结合司法辖区、机构、文件类型和 AI 政策术语完成译审"


def run() -> dict[str, int]:
    latest: dict[str, dict] = {}
    with REVIEWS.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                if record.get("review_version") == VERSION:
                    latest[record["policy_id"]] = record
    fields = [
        "policy_id", "language", "country_or_org", "issuer", "title_original",
        "title_zh_previous", "title_zh_reviewed", "final_status", "final_reason",
        "model", "review_version",
    ]
    counts: dict[str, int] = {}
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for policy_id in sorted(latest):
            record = latest[policy_id]
            status, reason = final_status(record["title_original"], record["title_zh_reviewed"])
            counts[status] = counts.get(status, 0) + 1
            writer.writerow({
                "policy_id": policy_id,
                "language": record.get("language", ""),
                "country_or_org": record.get("country_or_org", ""),
                "issuer": record.get("issuer", ""),
                "title_original": record["title_original"],
                "title_zh_previous": record.get("title_zh_previous", ""),
                "title_zh_reviewed": record["title_zh_reviewed"],
                "final_status": status,
                "final_reason": reason,
                "model": record.get("model", ""),
                "review_version": VERSION,
            })
    return counts


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
