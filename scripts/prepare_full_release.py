"""Copy recovered AI-policy code/databases into this GitHub export tree."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


EXPORT_ROOT = Path(__file__).resolve().parents[1]
COPY_DIRECTORIES = ("viewer", "data/processed")
COPY_FILES = ("requirements.txt", "检索窗口使用说明.md", "AI政策数据集说明文档.docx")


def copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.building.db", "*.log"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    copied: list[str] = []
    missing: list[str] = []
    for relative in COPY_DIRECTORIES:
        source = project_root / relative
        if source.is_dir():
            copy_tree(source, EXPORT_ROOT / relative)
            copied.append(relative)
        else:
            missing.append(relative)
    for relative in COPY_FILES:
        source = project_root / relative
        if source.is_file():
            destination = EXPORT_ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative)
        else:
            missing.append(relative)
    print("Copied:")
    for item in copied:
        print(f"  + {item}")
    print("Missing:")
    for item in missing:
        print(f"  - {item}")
    if missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

