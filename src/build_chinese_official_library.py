"""Create a standalone Chinese-language official-source library with copied raw files."""
from __future__ import annotations

import csv, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "data" / "official_zh"
PLACES = {"中国", "台湾", "香港", "澳门"}


def main() -> None:
    with (PROCESSED / "ai_policies_content_master.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("country_or_org") in PLACES and row.get("language") == "zh"]
        fields = handle.seek(0) or []
    OUT.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT / "raw"; raw_dir.mkdir(exist_ok=True)
    for row in rows:
        source = ROOT / row["raw_file"]
        target = raw_dir / source.name
        if source.exists() and not target.exists():
            shutil.copy2(source, target)
        row["raw_file_library"] = str(target.relative_to(ROOT)).replace("\\", "/")
    with (OUT / "chinese_official_ai_policies.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        keys = list(rows[0]) if rows else []
        writer = csv.DictWriter(handle, fieldnames=keys); writer.writeheader(); writer.writerows(rows)
    wanted = {row["policy_id"] for row in rows}
    with (PROCESSED / "policy_fulltexts.jsonl").open(encoding="utf-8") as source, (OUT / "chinese_official_policy_fulltexts.jsonl").open("w", encoding="utf-8") as target:
        for line in source:
            record = json.loads(line)
            if record.get("policy_id") in wanted:
                target.write(json.dumps(record, ensure_ascii=False) + "\n")
    (OUT / "README.md").write_text("# 中文官方原始文件库\n\n仅保留中文原始语言、已成功提取正文、来源校验通过的 AI 政策。`raw/` 为独立复制的官方原始 HTML/PDF；CSV 为结构化索引；JSONL 为完整正文。\n", encoding="utf-8")
    print(f"Chinese official library: {len(rows)} records; raw files copied to {raw_dir}")


if __name__ == "__main__":
    main()
