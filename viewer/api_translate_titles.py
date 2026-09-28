"""Review every non-Chinese clean-policy title with an OpenAI-compatible API."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "processed" / "ai_policies_cleaned.csv"
TRANSLATIONS = Path(__file__).resolve().parent / "title_translations.jsonl"
REVIEWS = Path(__file__).resolve().parent / "contextual_title_reviews.jsonl"
VERSION = "2026-07-external-contextual-v2"
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "policy_title_translation_zh.md"


def env_value(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    if winreg is not None:
        for root, subkey in (
            (winreg.HKEY_CURRENT_USER, "Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(root, subkey) as key:
                    return str(winreg.QueryValueEx(key, name)[0])
            except OSError:
                pass
    return ""


def is_chinese_language(language: str) -> bool:
    value = language.strip().lower()
    return value.startswith("zh") or value in {"chinese", "中文", "zho", "chi"}


def candidates() -> list[dict[str, str]]:
    with CLEAN.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if not is_chinese_language(row.get("language", ""))]
    priority = {"en": 0, "eng": 0, "und": 1, "": 1}
    rows.sort(key=lambda row: (priority.get((row.get("language") or "").lower(), 2), row.get("policy_id", "")))
    return rows


def previous_translations() -> dict[str, str]:
    result: dict[str, str] = {}
    if TRANSLATIONS.exists():
        with TRANSLATIONS.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    result[record["title_original"]] = record.get("title_zh", "")
    return result


def completed_ids() -> set[str]:
    result: set[str] = set()
    if REVIEWS.exists():
        with REVIEWS.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    if record.get("review_version") == VERSION:
                        result.add(record["policy_id"])
    return result


def build_prompt(batch: list[dict[str, str]]) -> str:
    payload = [
        {
            "id": index,
            "title": row["title_original"],
            "language": row.get("language", ""),
            "jurisdiction": row.get("country_or_org", ""),
            "issuer": row.get("issuer", ""),
            "document_type": row.get("policy_type", ""),
            "topics": row.get("topics", ""),
        }
        for index, row in enumerate(batch, 1)
    ]
    instructions = PROMPT_PATH.read_text(encoding="utf-8")
    return instructions + "\n\n## 本批输入\n\n" + json.dumps(payload, ensure_ascii=False)


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("响应中没有 JSON 对象")
    return json.loads(text[start:end + 1])


def call_api(batch: list[dict[str, str]], attempts: int = 4) -> list[str]:
    key = env_value("OPENAI_API_KEY")
    base = env_value("OPENAI_BASE_URL").rstrip("/")
    model = env_value("OPENAI_MODEL") or env_value("OPENAI_VISION_MODEL")
    if not key or not base or not model:
        raise RuntimeError("缺少 OPENAI_API_KEY、OPENAI_BASE_URL 或模型环境变量")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "你只执行严谨的政策标题中文译审，并严格返回 JSON。"},
            {"role": "user", "content": build_prompt(batch)},
        ],
        "temperature": 0,
        "max_tokens": max(1200, len(batch) * 110),
    }, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            base + "/chat/completions", data=body, method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            parsed = extract_json(content)
            items = parsed.get("items", [])
            by_id = {int(item["id"]): str(item["title_zh"]).strip() for item in items}
            if set(by_id) != set(range(1, len(batch) + 1)):
                raise ValueError("返回条目编号不完整")
            return [by_id[index] for index in range(1, len(batch) + 1)]
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API 批次失败：{last_error}")


def quality_flags(original: str, translated: str) -> list[str]:
    flags: list[str] = []
    if not re.search(r"[\u4e00-\u9fff]", translated):
        flags.append("缺少中文")
    if "adoption" in original.lower() and "收养" in translated:
        flags.append("AI adoption 误译")
    if len(translated) < 2 or len(translated) > max(140, len(original) * 4):
        flags.append("长度异常")
    if re.search(r"\b(?:AI|artificial intelligence)\b", original, re.I) and not (
        "人工智能" in translated or re.search(r"\bAI\b", translated, re.I)
    ):
        flags.append("AI 术语疑似遗漏")
    return flags


def chunks(rows: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


def run(batch_size: int, workers: int) -> None:
    rows = candidates()
    done_ids = completed_ids()
    previous = previous_translations()
    remaining = [row for row in rows if row["policy_id"] not in done_ids]
    batches = chunks(remaining, batch_size)
    print(f"目标 {len(rows):,} 条；已复核 {len(done_ids):,} 条；本次 {len(remaining):,} 条；共 {len(batches):,} 批", flush=True)
    if not remaining:
        return
    model = env_value("OPENAI_MODEL") or env_value("OPENAI_VISION_MODEL")
    finished = 0
    failures: list[list[dict[str, str]]] = []
    with REVIEWS.open("a", encoding="utf-8") as review_file, TRANSLATIONS.open("a", encoding="utf-8") as translations_file:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(call_api, batch): batch for batch in batches}
            for future in as_completed(future_map):
                batch = future_map[future]
                try:
                    translated_titles = future.result()
                except Exception as exc:
                    print(f"批次暂存失败：{batch[0]['policy_id']}；{exc}", flush=True)
                    failures.append(batch)
                    continue
                for row, translated in zip(batch, translated_titles, strict=True):
                    flags = quality_flags(row["title_original"], translated)
                    record = {
                        "policy_id": row["policy_id"], "title_original": row["title_original"],
                        "title_zh_previous": previous.get(row["title_original"], ""),
                        "title_zh_reviewed": translated, "language": row.get("language", ""),
                        "country_or_org": row.get("country_or_org", ""), "issuer": row.get("issuer", ""),
                        "quality_flags": flags, "review_status": "需再审" if flags else "AI上下文译审通过",
                        "model": model, "review_version": VERSION,
                    }
                    review_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    translations_file.write(json.dumps({
                        "title_original": row["title_original"], "title_zh": translated,
                        "source": "external_contextual_review", "review_version": VERSION,
                        "policy_id": row["policy_id"], "quality_flags": flags,
                    }, ensure_ascii=False) + "\n")
                review_file.flush()
                translations_file.flush()
                finished += len(batch)
                print(f"API 标题译审进度：{finished:,} / {len(remaining):,}", flush=True)
    if failures:
        raise RuntimeError(f"仍有 {sum(map(len, failures))} 条因 API 批次失败未完成，可重新运行断点续传")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run(max(1, min(args.batch_size, 30)), max(1, min(args.workers, 8)))


if __name__ == "__main__":
    main()
