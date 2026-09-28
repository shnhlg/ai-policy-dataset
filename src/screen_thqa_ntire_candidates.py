from __future__ import annotations

import csv
import http.client
import io
import json
import os
import shutil
import time
import urllib.request
import zipfile
from collections import OrderedDict
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "ai_short_drama_uncanny_mini" / "screening_pool"
VIDEO_DIR = OUT / "videos"
PREVIEW_DIR = OUT / "previews"

DATASET = "zyj2000/THQA-NTIRE"
COMMIT = "33a348bb0a524df440aa4eaa3ef24577ada5f5dd"
CSV_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/{COMMIT}/thqa_ntire_train.csv"
ZIP_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/{COMMIT}/train.zip"
USER_AGENT = "ai-short-drama-uncanny-screening/0.1"


class HttpRangeReader(io.RawIOBase):
    def __init__(self, url: str, block_size: int = 4 * 1024 * 1024, max_blocks: int = 12):
        self.url = url
        self.block_size = block_size
        self.max_blocks = max_blocks
        self.position = 0
        self.cache: OrderedDict[int, bytes] = OrderedDict()

        request = urllib.request.Request(
            self.url,
            headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            content_range = response.headers.get("Content-Range", "")
            if "/" not in content_range:
                raise RuntimeError("Remote server did not return a ranged response")
            self.length = int(content_range.rsplit("/", 1)[1])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            new_position = offset
        elif whence == os.SEEK_CUR:
            new_position = self.position + offset
        elif whence == os.SEEK_END:
            new_position = self.length + offset
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        if new_position < 0:
            raise ValueError("Negative seek position")
        self.position = min(new_position, self.length)
        return self.position

    def _get_block(self, block_index: int) -> bytes:
        if block_index in self.cache:
            block = self.cache.pop(block_index)
            self.cache[block_index] = block
            return block

        start = block_index * self.block_size
        end = min(self.length - 1, start + self.block_size - 1)
        expected = end - start + 1
        block = b""
        last_error: Exception | None = None
        for attempt in range(5):
            request = urllib.request.Request(
                self.url,
                headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"},
            )
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    block = response.read()
                if len(block) == expected:
                    break
                last_error = RuntimeError(
                    f"Short range read at {start}: expected {expected}, got {len(block)}"
                )
            except (OSError, TimeoutError, http.client.IncompleteRead) as error:
                last_error = error
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1))
        if len(block) != expected:
            raise RuntimeError(f"Range read failed at {start} after 5 attempts") from last_error

        self.cache[block_index] = block
        while len(self.cache) > self.max_blocks:
            self.cache.popitem(last=False)
        return block

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.length:
            return b""
        if size is None or size < 0:
            size = self.length - self.position
        size = min(size, self.length - self.position)

        remaining = size
        chunks: list[bytes] = []
        while remaining:
            block_index = self.position // self.block_size
            offset_in_block = self.position % self.block_size
            block = self._get_block(block_index)
            take = min(remaining, len(block) - offset_in_block)
            chunks.append(block[offset_in_block : offset_in_block + take])
            self.position += take
            remaining -= take
        return b"".join(chunks)

    def readinto(self, buffer: bytearray) -> int:
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def fetch_csv_rows() -> list[dict]:
    request = urllib.request.Request(CSV_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        text = response.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def choose_candidates(rows: list[dict]) -> list[dict]:
    chosen: list[dict] = []

    def choose(prompt_id: str, model: str, target_score: float = 2.5) -> None:
        candidates = []
        for row in rows:
            filename = row["Video"]
            stem = Path(filename).stem
            pieces = stem.split("_")
            if len(pieces) < 4:
                continue
            if pieces[0] != prompt_id or pieces[1] != model:
                continue
            if pieces[-1] != "dreamtalk":
                continue
            candidates.append(row)
        if not candidates:
            raise RuntimeError(f"No candidate for prompt={prompt_id}, model={model}, method=dreamtalk")
        selected = min(candidates, key=lambda row: (abs(float(row["Score"]) - target_score), row["Video"]))
        if selected["Video"] not in {item["Video"] for item in chosen}:
            chosen.append(selected)

    for prompt_id in ["8", "9", "15", "17", "18", "22", "23", "24", "25"]:
        choose(prompt_id, "dalle3")
    for model in ["flux", "fooocus", "idea", "sd3"]:
        choose("15", model)

    return chosen


def extract_candidates(candidates: list[dict]) -> None:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    remote = HttpRangeReader(ZIP_URL)
    with zipfile.ZipFile(remote) as archive:
        entry_by_basename: dict[str, str] = {}
        for name in archive.namelist():
            basename = Path(name).name
            if basename:
                entry_by_basename[basename] = name

        for candidate in candidates:
            filename = candidate["Video"]
            entry = entry_by_basename.get(filename)
            if entry is None:
                raise FileNotFoundError(f"{filename} is not present in train.zip")
            destination = VIDEO_DIR / filename
            if destination.exists() and destination.stat().st_size > 0:
                continue
            partial = destination.with_suffix(destination.suffix + ".part")
            with archive.open(entry) as source, partial.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            os.replace(partial, destination)
            print(f"extracted {filename}")


def video_frames(path: Path) -> list[Image.Image]:
    capture = cv2.VideoCapture(str(path))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    frames: list[Image.Image] = []
    for fraction in (0.2, 0.5, 0.8):
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, round((frame_count - 1) * fraction)))
        ok, frame = capture.read()
        if not ok:
            continue
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(Image.fromarray(frame))
    capture.release()
    return frames


def write_screening_manifest(candidates: list[dict]) -> None:
    with (OUT / "screening_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "video",
            "mos_score",
            "prompt_id",
            "image_model",
            "talker_method",
            "local_path",
            "source_dataset",
            "source_commit",
            "license",
            "adult_appearance_review",
            "target_style_review_0_3",
            "include_in_target_set",
            "review_notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in candidates:
            pieces = Path(item["Video"]).stem.split("_")
            writer.writerow(
                {
                    "video": item["Video"],
                    "mos_score": item["Score"],
                    "prompt_id": pieces[0],
                    "image_model": pieces[1],
                    "talker_method": pieces[-1],
                    "local_path": (VIDEO_DIR / item["Video"]).relative_to(OUT).as_posix(),
                    "source_dataset": DATASET,
                    "source_commit": COMMIT,
                    "license": "MIT",
                }
            )


def make_contact_sheet(candidates: list[dict]) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    tile_width, tile_height = 260, 228
    label_width = 170
    sheet = Image.new("RGB", (label_width + tile_width * 3, tile_height * len(candidates)), "white")
    draw = ImageDraw.Draw(sheet)

    for row_index, item in enumerate(candidates):
        filename = item["Video"]
        pieces = Path(filename).stem.split("_")
        label = f"id {pieces[0]} | {pieces[1]}\nMOS {item['Score']}"
        draw.multiline_text((8, row_index * tile_height + 92), label, fill="black", spacing=4)
        for column_index, frame in enumerate(video_frames(VIDEO_DIR / filename)):
            tile = ImageOps.fit(frame.convert("RGB"), (tile_width - 4, tile_height - 4), method=Image.Resampling.LANCZOS)
            x = label_width + column_index * tile_width + 2
            y = row_index * tile_height + 2
            sheet.paste(tile, (x, y))
    sheet.save(PREVIEW_DIR / "candidate_contact_sheet.jpg", quality=90)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = fetch_csv_rows()
    candidates = choose_candidates(rows)
    extract_candidates(candidates)
    write_screening_manifest(candidates)
    make_contact_sheet(candidates)
    summary = {"candidate_count": len(candidates), "source": DATASET, "commit": COMMIT}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
