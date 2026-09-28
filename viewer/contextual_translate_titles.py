"""Context-aware LLM review of 2,000 non-Chinese policy titles."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "processed" / "ai_policies_cleaned.csv"
TRANSLATIONS = Path(__file__).resolve().parent / "title_translations.jsonl"
REVIEWS = Path(__file__).resolve().parent / "contextual_title_reviews.jsonl"
MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
VERSION = "2026-07-contextual-v1"


def is_chinese_language(language: str) -> bool:
    value = language.strip().lower()
    return value.startswith("zh") or value in {"chinese", "中文", "zho", "chi"}


def load_candidates() -> list[dict[str, str]]:
    with CLEAN.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if not is_chinese_language(row.get("language", ""))]
    priority = {"en": 0, "eng": 0, "und": 1, "": 1}
    rows.sort(key=lambda row: (priority.get((row.get("language") or "").lower(), 2), row.get("policy_id", "")))
    return rows


def load_previous_translations() -> dict[str, str]:
    result: dict[str, str] = {}
    if TRANSLATIONS.exists():
        with TRANSLATIONS.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    result[record["title_original"]] = record.get("title_zh", "")
    return result


def load_completed() -> dict[str, dict]:
    result: dict[str, dict] = {}
    if REVIEWS.exists():
        with REVIEWS.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    if record.get("review_version") == VERSION:
                        result[record["policy_id"]] = record
    return result


def prompt_for(batch: list[dict[str, str]]) -> str:
    lines = []
    for index, row in enumerate(batch, 1):
        context = "；".join(filter(None, [
            row.get("country_or_org", ""), row.get("issuer", ""),
            row.get("policy_type", ""), row.get("topics", ""),
        ]))
        lines.append(f"{index}\t标题：{row['title_original']}\t语境：{context}")
    return """你是精通人工智能治理与公共政策的资深中文译审。请把下面政策标题翻译成准确、自然、正式的简体中文。

硬性要求：
1. 根据 AI 政策语境消歧；AI adoption 译为“人工智能应用/采用/推广”，绝不能译为“人工智能收养”。
2. privacy notice 译为“隐私声明/隐私通知”；guidance 译为“指南/指导意见”；regulation 按语境译为“条例/法规”。
3. Artificial Intelligence 首次出现译为“人工智能”，AI 可保留在专有项目名或括号中。
4. 保留法令编号、年份、机构专名和项目专名；不扩写标题中没有的信息。
5. 只输出与输入相同数量的行，格式严格为：编号<TAB>中文译名。不要解释，不要使用 Markdown。

待译标题：
""" + "\n".join(lines)


def parse_output(text: str, expected: int) -> list[str] | None:
    found: dict[int, str] = {}
    for raw in text.splitlines():
        line = raw.strip().strip("`")
        match = re.match(r"^(\d+)\s*(?:\t|[.、:：]\s*)(.+)$", line)
        if match:
            found[int(match.group(1))] = match.group(2).strip().strip('"“”')
    if set(found) != set(range(1, expected + 1)):
        return None
    return [found[index] for index in range(1, expected + 1)]


def quality_flags(original: str, translated: str) -> list[str]:
    flags: list[str] = []
    if not re.search(r"[\u4e00-\u9fff]", translated):
        flags.append("缺少中文")
    if "adoption" in original.lower() and "收养" in translated:
        flags.append("AI adoption 误译")
    if len(translated) < 2 or len(translated) > max(120, len(original) * 4):
        flags.append("长度异常")
    if translated.count("人工智能") + translated.upper().count("AI") == 0 and re.search(
        r"\b(?:AI|artificial intelligence)\b", original, re.I
    ):
        flags.append("AI 术语疑似遗漏")
    return flags


def run(batch_size: int) -> None:
    candidates = load_candidates()
    previous = load_previous_translations()
    completed = load_completed()
    remaining = [row for row in candidates if row["policy_id"] not in completed]
    print(f"目标 {len(candidates):,} 条；已复核 {len(completed):,} 条；待处理 {len(remaining):,} 条", flush=True)
    if not remaining:
        return
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, torch_dtype=torch.bfloat16,
    ).to("cuda")
    model.eval()
    done = 0
    with REVIEWS.open("a", encoding="utf-8") as review_file, TRANSLATIONS.open("a", encoding="utf-8") as translation_file:
        for start in range(0, len(remaining), batch_size):
            batch = remaining[start:start + batch_size]
            messages = [
                {"role": "system", "content": "你只进行严谨的政策标题中译，不回答其他问题。"},
                {"role": "user", "content": prompt_for(batch)},
            ]
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = tokenizer(text, return_tensors="pt").to("cuda")
            with torch.inference_mode():
                generated = model.generate(
                    **inputs, max_new_tokens=max(160, 55 * len(batch)), do_sample=False,
                    repetition_penalty=1.05, pad_token_id=tokenizer.eos_token_id,
                )
            answer = tokenizer.decode(generated[0, inputs.input_ids.shape[1]:], skip_special_tokens=True)
            translations = parse_output(answer, len(batch))
            if translations is None:
                # A single-item retry is easier to parse and prevents an entire batch being lost.
                translations = []
                for row in batch:
                    one_messages = [messages[0], {"role": "user", "content": prompt_for([row])}]
                    one_text = tokenizer.apply_chat_template(one_messages, tokenize=False, add_generation_prompt=True)
                    one_inputs = tokenizer(one_text, return_tensors="pt").to("cuda")
                    with torch.inference_mode():
                        one_generated = model.generate(
                            **one_inputs, max_new_tokens=120, do_sample=False,
                            pad_token_id=tokenizer.eos_token_id,
                        )
                    one_answer = tokenizer.decode(one_generated[0, one_inputs.input_ids.shape[1]:], skip_special_tokens=True)
                    parsed = parse_output(one_answer, 1)
                    translations.append(parsed[0] if parsed else previous.get(row["title_original"], row["title_original"]))
            for row, translated in zip(batch, translations, strict=True):
                flags = quality_flags(row["title_original"], translated)
                record = {
                    "policy_id": row["policy_id"],
                    "title_original": row["title_original"],
                    "title_zh_previous": previous.get(row["title_original"], ""),
                    "title_zh_reviewed": translated,
                    "language": row.get("language", ""),
                    "country_or_org": row.get("country_or_org", ""),
                    "issuer": row.get("issuer", ""),
                    "quality_flags": flags,
                    "review_status": "需再审" if flags else "AI上下文译审通过",
                    "model": MODEL_ID,
                    "review_version": VERSION,
                }
                review_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                translation_file.write(json.dumps({
                    "title_original": row["title_original"], "title_zh": translated,
                    "source": "contextual_llm_review", "review_version": VERSION,
                    "policy_id": row["policy_id"], "quality_flags": flags,
                }, ensure_ascii=False) + "\n")
            review_file.flush()
            translation_file.flush()
            done += len(batch)
            print(f"标题译审进度：{done:,} / {len(remaining):,}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=6)
    args = parser.parse_args()
    run(max(1, min(args.batch_size, 12)))


if __name__ == "__main__":
    main()
