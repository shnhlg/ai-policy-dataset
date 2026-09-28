from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "uncanny_valley_mini"
IMAGE_DIR = OUT / "images"
VIDEO_DIR = OUT / "videos"
PREVIEW_DIR = OUT / "previews"

IMAGE_DATASET = "RichardErkhov/OneMillionFaces"
IMAGE_COMMIT = "994602d29fe96cc11d3d4a50d436801ce73fdae3"
IMAGE_LICENSE = "MIT (dataset card metadata)"
IMAGE_ROW_IDS = [index for index in range(33) if index not in {6, 16, 29}]

VIDEO_DATASET = "AIM-SCU/MAVEN_Multicultura_Text-to-Video_Generation"
VIDEO_COMMIT = "984801518f8883e2ca5491312f7828959ec4da86"
VIDEO_LICENSE = "CC0-1.0"

# Each pipeline contains 243 prompts in the same order. These three base
# positions cover food, music, and dance across Chinese, American, and
# Romanian subjects. Adding 243 selects the same prompt in the next pipeline.
VIDEO_BASE_ROWS = [0, 36, 72]
VIDEO_PIPELINE_OFFSETS = [0, 243, 486, 729]

USER_AGENT = "uncanny-valley-mini-dataset/0.1 (research sample collector)"


def request_json(url: str, retries: int = 4) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception as exc:  # noqa: BLE001 - retry network failures
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Unable to fetch JSON after {retries} attempts: {url}") from last_error


def download(url: str, destination: Path, retries: int = 4) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return

    part = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response, part.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            os.replace(part, destination)
            return
        except Exception as exc:  # noqa: BLE001 - retry network failures
            last_error = exc
            part.unlink(missing_ok=True)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Unable to download after {retries} attempts: {url}") from last_error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def video_duration(path: Path) -> float | None:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return round(float(result.stdout.strip()), 3)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def image_rows() -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "dataset": IMAGE_DATASET,
            "config": "default",
            "split": "train",
            "offset": 0,
            "length": 33,
        }
    )
    payload = request_json(f"https://datasets-server.huggingface.co/rows?{query}")
    rows = [item for item in payload.get("rows", []) if int(item["row_idx"]) in IMAGE_ROW_IDS]
    if len(rows) != 30:
        raise RuntimeError("Expected 30 adult-appearance image candidates from the Dataset Viewer API")
    return rows


def video_rows() -> list[dict]:
    rows: list[dict] = []
    for pipeline_offset in VIDEO_PIPELINE_OFFSETS:
        for base_row in VIDEO_BASE_ROWS:
            row_index = pipeline_offset + base_row
            query = urllib.parse.urlencode(
                {
                    "dataset": VIDEO_DATASET,
                    "config": "default",
                    "split": "train",
                    "offset": row_index,
                    "length": 1,
                }
            )
            payload = request_json(f"https://datasets-server.huggingface.co/rows?{query}")
            item = payload.get("rows", [])
            if len(item) != 1:
                raise RuntimeError(f"Expected one video row at offset {row_index}")
            rows.append(item[0])
    return rows


def prepare_jobs(image_items: list[dict], video_items: list[dict]) -> list[tuple[str, Path]]:
    jobs: list[tuple[str, Path]] = []
    for item in image_items:
        row_index = int(item["row_idx"])
        url = item["row"]["png"]["src"]
        jobs.append((url, IMAGE_DIR / f"uv_img_{row_index:04d}.jpg"))

    for item in video_items:
        row = item["row"]
        row_index = int(item["row_idx"])
        safe_pipeline = str(row["pipeline"]).replace("/", "-")
        filename = f"uv_vid_{row_index:04d}_{safe_pipeline}_{row['video_id']}.mp4"
        jobs.append((row["video"]["src"], VIDEO_DIR / filename))
    return jobs


def run_downloads(jobs: list[tuple[str, Path]]) -> None:
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(download, url, path): path for url, path in jobs}
        for future in as_completed(futures):
            path = futures[future]
            future.result()
            print(f"downloaded {path.relative_to(ROOT)}")


def build_manifest(image_items: list[dict], video_items: list[dict]) -> list[dict]:
    collected_at = datetime.now(timezone.utc).isoformat()
    records: list[dict] = []

    for item in image_items:
        row_index = int(item["row_idx"])
        row = item["row"]
        path = IMAGE_DIR / f"uv_img_{row_index:04d}.jpg"
        records.append(
            {
                "sample_id": f"uv_img_{row_index:04d}",
                "media_type": "image",
                "local_path": path.relative_to(OUT).as_posix(),
                "source_dataset": IMAGE_DATASET,
                "source_page": f"https://huggingface.co/datasets/{IMAGE_DATASET}",
                "source_commit": IMAGE_COMMIT,
                "source_row": row_index,
                "source_key": row["__key__"],
                "source_container": row["__url__"],
                "license": IMAGE_LICENSE,
                "pipeline": "",
                "culture": "",
                "person": "synthetic face",
                "action": "",
                "action_type": "",
                "location": "",
                "original_prompt": "",
                "width": row["png"]["width"],
                "height": row["png"]["height"],
                "duration_seconds": "",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "collected_at_utc": collected_at,
                "label_status": "unlabeled_candidate",
            }
        )

    for item in video_items:
        row_index = int(item["row_idx"])
        row = item["row"]
        safe_pipeline = str(row["pipeline"]).replace("/", "-")
        filename = f"uv_vid_{row_index:04d}_{safe_pipeline}_{row['video_id']}.mp4"
        path = VIDEO_DIR / filename
        source_url = row["video"]["src"]
        records.append(
            {
                "sample_id": path.stem,
                "media_type": "video",
                "local_path": path.relative_to(OUT).as_posix(),
                "source_dataset": VIDEO_DATASET,
                "source_page": f"https://huggingface.co/datasets/{VIDEO_DATASET}",
                "source_commit": VIDEO_COMMIT,
                "source_row": row_index,
                "source_key": row["video_id"],
                "source_container": source_url,
                "license": VIDEO_LICENSE,
                "pipeline": row["pipeline"],
                "culture": row["culture"],
                "person": row["person"],
                "action": row["action"],
                "action_type": row["action_type"],
                "location": row["location"],
                "original_prompt": row["original_prompt"],
                "width": "",
                "height": "",
                "duration_seconds": video_duration(path) or "",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "collected_at_utc": collected_at,
                "label_status": "unlabeled_candidate",
            }
        )

    return records


def write_manifests(records: list[dict]) -> None:
    fieldnames = list(records[0].keys())
    with (OUT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    with (OUT / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    annotation_fields = [
        "sample_id",
        "media_type",
        "uncanny_score_1_7",
        "human_likeness_1_7",
        "realism_1_7",
        "eeriness_1_7",
        "artifact_tags",
        "notes",
    ]
    with (OUT / "annotation_template.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=annotation_fields)
        writer.writeheader()
        for record in records:
            writer.writerow({"sample_id": record["sample_id"], "media_type": record["media_type"]})


def make_image_contact_sheet(records: list[dict]) -> None:
    image_records = [record for record in records if record["media_type"] == "image"]
    tile_width, tile_height = 180, 204
    columns = 6
    rows = math.ceil(len(image_records) / columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), "white")
    draw = ImageDraw.Draw(sheet)

    for position, record in enumerate(image_records):
        image = Image.open(OUT / record["local_path"]).convert("RGB")
        image = ImageOps.fit(image, (176, 176), method=Image.Resampling.LANCZOS)
        x = (position % columns) * tile_width + 2
        y = (position // columns) * tile_height + 2
        sheet.paste(image, (x, y))
        draw.text((x + 3, y + 180), record["sample_id"], fill="black")

    sheet.save(PREVIEW_DIR / "image_contact_sheet.jpg", quality=90)


def make_video_contact_sheet(records: list[dict]) -> None:
    video_records = [record for record in records if record["media_type"] == "video"]
    tile_width, tile_height = 320, 208
    columns = 3
    rows = math.ceil(len(video_records) / columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), "white")
    draw = ImageDraw.Draw(sheet)

    for position, record in enumerate(video_records):
        path = OUT / record["local_path"]
        capture = cv2.VideoCapture(str(path))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_count // 2))
        ok, frame = capture.read()
        capture.release()
        if not ok:
            continue
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame)
        image = ImageOps.fit(image, (316, 176), method=Image.Resampling.LANCZOS)
        x = (position % columns) * tile_width + 2
        y = (position // columns) * tile_height + 2
        sheet.paste(image, (x, y))
        label = f"{record['pipeline']} | {record['culture']} | {record['action_type']}"
        draw.text((x + 3, y + 180), label, fill="black")

    sheet.save(PREVIEW_DIR / "video_contact_sheet.jpg", quality=90)


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    images = image_rows()
    videos = video_rows()
    jobs = prepare_jobs(images, videos)
    run_downloads(jobs)

    records = build_manifest(images, videos)
    write_manifests(records)
    make_image_contact_sheet(records)
    make_video_contact_sheet(records)
    print(f"ready: {len(records)} samples in {OUT}")


if __name__ == "__main__":
    main()
