"""Offline multilingual semantic review for ambiguous AI-policy records."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


VIEWER = Path(__file__).resolve().parent
DB_PATH = VIEWER / "policy_search.db"
OUTPUT = VIEWER / "ai_review_results.jsonl"
MODEL_ID = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
VERSION = "2026-07-v2"
TITLE_HYPOTHESIS = (
    "This document title specifically describes an artificial intelligence policy, "
    "regulation, governance measure, strategy, standard, programme, or official AI initiative."
)
CONTENT_HYPOTHESIS = (
    "This official document is substantively about artificial intelligence policy, "
    "regulation, governance, strategy, standards, public funding, public-sector use, "
    "or an AI research and innovation initiative."
)


def load_records() -> list[dict[str, str]]:
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""
            SELECT policy_id,title_original,title_zh,country_or_org,issuer,policy_type,
                   topics,content_summary_original,policy_objectives,policy_measures,
                   regulatory_requirements,relevance_level
            FROM policies
            WHERE relevance_level IN ('待复核','可能相关')
            ORDER BY id
        """).fetchall()
    return [dict(row) for row in rows]


def review_text(row: dict[str, str]) -> str:
    parts = [
        "Title: " + (row.get("title_original") or ""),
        "Chinese title: " + (row.get("title_zh") or ""),
        "Issuer: " + (row.get("issuer") or ""),
        "Document type: " + (row.get("policy_type") or ""),
        "Topics: " + (row.get("topics") or ""),
        "Summary: " + (row.get("content_summary_original") or ""),
        "Objectives: " + (row.get("policy_objectives") or ""),
        "Measures: " + (row.get("policy_measures") or ""),
        "Requirements: " + (row.get("regulatory_requirements") or ""),
    ]
    return "\n".join(part for part in parts if part.split(": ", 1)[-1].strip())


def load_existing() -> dict[str, dict]:
    results: dict[str, dict] = {}
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    if record.get("review_version") == VERSION:
                        results[record["policy_id"]] = record
    return results


def decision(title_score: float, content_score: float) -> str:
    if title_score >= 0.93 or (title_score >= 0.72 and content_score >= 0.92):
        return "AI复核相关"
    if title_score <= 0.12 and content_score <= 0.50:
        return "AI复核无关"
    return "待人工复核"


def run(batch_size: int, limit: int | None) -> None:
    records = load_records()
    existing = load_existing()
    remaining = [row for row in records if row["policy_id"] not in existing]
    if limit is not None:
        remaining = remaining[:limit]
    print(f"语义复核目标 {len(records):,} 条；已完成 {len(existing):,} 条；本次处理 {len(remaining):,} 条。", flush=True)
    if not remaining:
        return
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"正在加载 {MODEL_ID} 到 {device}……", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID).to(device)
    if device.type == "cuda":
        model.half()
    model.eval()
    labels = {str(name).lower(): int(index) for index, name in model.config.id2label.items()}
    entailment_index = labels["entailment"]
    contradiction_index = labels["contradiction"]
    completed = 0
    with OUTPUT.open("a", encoding="utf-8") as output:
        for start in range(0, len(remaining), batch_size):
            batch = remaining[start:start + batch_size]
            def infer(premises: list[str], hypothesis: str, max_length: int) -> list[float]:
                encoded = tokenizer(
                    premises, [hypothesis] * len(batch), return_tensors="pt",
                    padding=True, truncation=True, max_length=max_length,
                ).to(device)
                with torch.inference_mode():
                    logits = model(**encoded).logits.float()
                pair_logits = logits[:, [contradiction_index, entailment_index]]
                return torch.softmax(pair_logits, dim=1)[:, 1].cpu().tolist()

            title_scores = infer([row["title_original"] for row in batch], TITLE_HYPOTHESIS, 192)
            content_scores = infer([review_text(row) for row in batch], CONTENT_HYPOTHESIS, 512)
            for row, title_score, content_score in zip(batch, title_scores, content_scores, strict=True):
                result = {
                    "policy_id": row["policy_id"],
                    "source_relevance": row["relevance_level"],
                    "title_ai_probability": round(float(title_score), 6),
                    "content_ai_probability": round(float(content_score), 6),
                    "ai_probability": round(float((title_score * 0.7) + (content_score * 0.3)), 6),
                    "ai_review_decision": decision(float(title_score), float(content_score)),
                    "model": MODEL_ID,
                    "review_version": VERSION,
                    "reason": f"标题语义 {title_score:.1%}；内容语义 {content_score:.1%}",
                }
                output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()
            completed += len(batch)
            print(f"AI 复核进度：{completed:,} / {len(remaining):,}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run(max(1, args.batch_size), args.limit)


if __name__ == "__main__":
    main()
