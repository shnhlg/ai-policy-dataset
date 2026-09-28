"""Turn cached multilingual model scores into traceable, source-aware decisions."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = Path(__file__).resolve().parent / "ai_review_results.jsonl"
MASTER = ROOT / "data" / "processed" / "ai_policies_content_master.csv"
VERSION = "2026-07-source-aware-v1"
SCORE_VERSION = "2026-07-v2"
OUTPUTS = {
    "clean": ROOT / "data" / "processed" / "ai_policies_cleaned.csv",
    "quarantine": ROOT / "data" / "processed" / "ai_policies_quarantine.csv",
    "manual": ROOT / "data" / "processed" / "ai_policies_manual_review.csv",
}


def load_scores() -> dict[str, dict]:
    latest: dict[str, dict] = {}
    if not INPUT.exists():
        return latest
    with INPUT.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                if record.get("review_version") == SCORE_VERSION:
                    latest[record["policy_id"]] = record
    return latest


def source_group(policy_id: str) -> str:
    if policy_id.startswith("OECD-LINK-"):
        return "OECD精选库"
    if policy_id.startswith(("CN-", "HK-", "MO-", "TW-")):
        return "中文官方库"
    if policy_id.startswith("US-FR-"):
        return "美国联邦公报"
    return "其他来源"


def decide(policy_id: str, title_score: float, content_score: float) -> tuple[str, str]:
    group = source_group(policy_id)
    if group == "OECD精选库":
        related = (
            (title_score >= 0.28 and content_score >= 0.50)
            or title_score >= 0.35
            or (content_score >= 0.93 and title_score >= 0.18)
        )
        unrelated = title_score <= 0.08 and content_score <= 0.30
    elif group == "中文官方库":
        related = title_score >= 0.25 and content_score >= 0.85
        unrelated = title_score <= 0.08 and content_score <= 0.30
    elif group == "美国联邦公报":
        # Broad keyword collection generated heavy noise. Explicit AI terminology was
        # already accepted by the deterministic first pass, so this pass only removes
        # weak semantic matches and leaves stronger borderline cases for human review.
        related = False
        unrelated = title_score <= 0.25 and content_score <= 0.92
    else:
        related = (title_score >= 0.35 and content_score >= 0.75) or title_score >= 0.50
        unrelated = title_score <= 0.08 and content_score <= 0.30
    if related:
        return "AI复核相关", f"{group}来源校准后，标题与正文语义共同支持 AI 政策相关性"
    if unrelated:
        return "AI复核无关", f"{group}来源校准后，标题与正文均缺少足够的 AI 政策语义证据"
    return "待人工复核", f"{group}来源校准后证据仍不充分，保留供人工复核"


def finalized_reviews() -> dict[str, dict]:
    final: dict[str, dict] = {}
    for policy_id, record in load_scores().items():
        title_score = float(record["title_ai_probability"])
        content_score = float(record["content_ai_probability"])
        decision, explanation = decide(policy_id, title_score, content_score)
        final[policy_id] = {
            **record,
            "ai_review_decision": decision,
            "ai_review_reason": (
                f"{explanation}；标题语义 {title_score:.1%}，正文语义 {content_score:.1%}"
            ),
            "ai_review_version": VERSION,
            "ai_review_source_group": source_group(policy_id),
        }
    return final


def export() -> dict[str, int]:
    reviews = finalized_reviews()
    with MASTER.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        input_fields = list(reader.fieldnames or [])
    extra_fields = [
        "ai_review_decision", "ai_review_reason", "ai_title_probability",
        "ai_content_probability", "ai_review_model", "ai_review_version",
        "ai_review_source_group",
    ]
    handles = {key: path.open("w", encoding="utf-8-sig", newline="") for key, path in OUTPUTS.items()}
    writers = {key: csv.DictWriter(handle, fieldnames=input_fields + extra_fields) for key, handle in handles.items()}
    for writer in writers.values():
        writer.writeheader()
    counts = {"clean": 0, "quarantine": 0, "manual": 0}
    try:
        for row in rows:
            review = reviews.get((row.get("policy_id") or "").strip())
            if review:
                decision = review["ai_review_decision"]
                row.update({
                    "ai_review_decision": decision,
                    "ai_review_reason": review["ai_review_reason"],
                    "ai_title_probability": review["title_ai_probability"],
                    "ai_content_probability": review["content_ai_probability"],
                    "ai_review_model": review["model"],
                    "ai_review_version": review["ai_review_version"],
                    "ai_review_source_group": review["ai_review_source_group"],
                })
                bucket = "clean" if decision == "AI复核相关" else "quarantine" if decision == "AI复核无关" else "manual"
            else:
                row.update({field: "" for field in extra_fields})
                row["ai_review_decision"] = "规则明确相关"
                row["ai_review_reason"] = "第一轮明确 AI 关键词与政策语境规则已确认"
                bucket = "clean"
            writers[bucket].writerow(row)
            counts[bucket] += 1
    finally:
        for handle in handles.values():
            handle.close()
    return counts


if __name__ == "__main__":
    result = export()
    print(json.dumps(result, ensure_ascii=False))
