"""Translate unique English policy titles to Simplified Chinese with a local model."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import torch
from fast_langdetect import detect
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "processed" / "ai_policies_content_master.csv"
CACHE_PATH = Path(__file__).resolve().parent / "title_translations.jsonl"
MODEL_ID = "Helsinki-NLP/opus-mt-en-zh"
ENGLISH_LANGUAGES = {"en", "eng"}


def looks_english(title: str) -> bool:
    if not re.search(r"[A-Za-z]{4}", title) or re.search(r"[\u3400-\u9fff]", title):
        return False
    try:
        candidate = detect(title, model="lite", k=1)[0]
        return candidate.get("lang") == "en" and float(candidate.get("score", 0)) >= 0.45
    except (IndexError, KeyError, TypeError, ValueError):
        return False


def load_targets() -> list[str]:
    targets: set[str] = set()
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            title = (row.get("title_original") or "").strip()
            language = (row.get("language") or "").strip().lower()
            if title and language in ENGLISH_LANGUAGES | {"und"} and looks_english(title):
                targets.add(title)
    return sorted(targets)


def load_existing() -> dict[str, str]:
    existing: dict[str, str] = {}
    if CACHE_PATH.exists():
        with CACHE_PATH.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    existing[record["title_original"]] = record["title_zh"]
    return existing


def translate(batch_size: int, limit: int | None) -> None:
    targets = load_targets()
    existing = load_existing()
    remaining = [title for title in targets if title not in existing]
    if limit is not None:
        remaining = remaining[:limit]
    print(f"英文标题共 {len(targets):,} 个；已缓存 {len(existing):,} 个；本次处理 {len(remaining):,} 个。", flush=True)
    if not remaining:
        return
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"正在加载翻译模型到 {device}……", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID).to(device)
    if device.type == "cuda":
        model.half()
    model.eval()
    completed = 0
    with CACHE_PATH.open("a", encoding="utf-8") as output:
        for start in range(0, len(remaining), batch_size):
            titles = remaining[start:start + batch_size]
            inputs = tokenizer(
                [">>cmn_Hans<< " + title for title in titles],
                return_tensors="pt", padding=True, truncation=True, max_length=384,
            ).to(device)
            with torch.inference_mode():
                generated = model.generate(
                    **inputs, max_new_tokens=384, num_beams=4,
                    renormalize_logits=True, early_stopping=True,
                )
            translations = tokenizer.batch_decode(generated, skip_special_tokens=True)
            for title, translated in zip(titles, translations, strict=True):
                translated = translated.strip() or title
                output.write(json.dumps({
                    "title_original": title, "title_zh": translated,
                    "model": MODEL_ID,
                }, ensure_ascii=False) + "\n")
            output.flush()
            completed += len(titles)
            print(f"翻译进度：{completed:,} / {len(remaining):,}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    translate(max(1, args.batch_size), args.limit)


if __name__ == "__main__":
    main()
