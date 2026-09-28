from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "ai_short_drama_uncanny_mini"
REFERENCE_DIR = OUT / "reference_only"
SOURCE_POOL = OUT / "appearance_screening" / "videos"
DYNAMIC_DIR = OUT / "licensed_dynamic_candidates"
PREVIEW_DIR = OUT / "previews"

DATASET = "zyj2000/THQA-NTIRE"
DATASET_COMMIT = "33a348bb0a524df440aa4eaa3ef24577ada5f5dd"
DATASET_PAGE = "https://huggingface.co/datasets/zyj2000/THQA-NTIRE"
DATASET_LICENSE = "MIT (dataset card); review source-portrait rights before public release"

REFERENCE_FILES = [
    (
        Path(r"C:\Users\Paulx\AppData\Local\Temp\codex-clipboard-259ab49a-ce39-443e-887f-7315790d0412.jpg"),
        "ref_01_ai_drama_face_grid.jpg",
        "target_positive_reference",
        "AI短剧脸九宫格；含明显未成年人外观角色，仅作研究参照，不进入可发布训练集。",
    ),
    (
        Path(r"C:\Users\Paulx\AppData\Local\Temp\codex-clipboard-6ccb7ef6-1213-41f4-950c-1f33c04d24f0.png"),
        "ref_02_closeup_plastic_skin.png",
        "target_positive_reference",
        "高写实AI女性近景：大眼、窄鼻、冷白磨皮、模板化五官与表情联动可疑。",
    ),
    (
        Path(r"C:\Users\Paulx\AppData\Local\Temp\codex-clipboard-a0aea100-8203-447f-aa89-9ca4be8c8d4e.png"),
        "ref_03_exaggerated_expression_grid.png",
        "target_or_control_reference",
        "夸张情绪表情对照；是否全部为AI生成尚未核验，不作为真值。",
    ),
    (
        Path(r"C:\Users\Paulx\AppData\Local\Temp\codex-clipboard-dd2ac66d-ef80-49bb-bf20-0866904439b1.jpg"),
        "ref_04_ai_drama_social_post.jpg",
        "target_positive_reference",
        "社交平台AI短剧脸讨论截图，强调空洞眼神、塑料皮肤和僵硬表情切换。",
    ),
]

# Visual screening retained only adult-appearing, photorealistic female portraits.
# Prompt groups 2 and 8 were excluded as minor-like or age-ambiguous; group 9 was
# excluded as age-ambiguous. Prompt group 14 contains the retained adult portraits.
SELECTED_VIDEOS = [
    "14_dalle3_common_voice_en_35729060_wavlip.mp4",
    "14_flux_common_voice_en_35729060_wavlip.mp4",
    "14_fooocus_common_voice_en_35729062_wavlip.mp4",
    "14_idea_common_voice_en_35729059_wavlip.mp4",
    "14_kandinsky_common_voice_en_35729059_wavlip.mp4",
    "14_mid_common_voice_en_35729066_wavlip.mp4",
    "14_opendalle11_common_voice_en_35729066_wavlip.mp4",
    "14_proteus_common_voice_en_35729066_wavlip.mp4",
    "14_sd1_common_voice_en_35729066_wavlip.mp4",
    "14_sd15_common_voice_en_35729068_wavlip.mp4",
    "14_sd3_common_voice_en_35729060_wavlip.mp4",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_inputs() -> None:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    DYNAMIC_DIR.mkdir(parents=True, exist_ok=True)
    for source, name, _, _ in REFERENCE_FILES:
        if not source.exists():
            raise FileNotFoundError(f"Missing user reference: {source}")
        shutil.copy2(source, REFERENCE_DIR / name)
    for name in SELECTED_VIDEOS:
        source = SOURCE_POOL / name
        if not source.exists():
            raise FileNotFoundError(
                f"Missing screened source video: {source}. Run screen_thqa_ntire_appearance.py first."
            )
        shutil.copy2(source, DYNAMIC_DIR / name)


def read_scores() -> dict[str, str]:
    path = OUT / "appearance_screening" / "screening_manifest.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["video"]: row["mos_score"] for row in csv.DictReader(handle)}


def video_metadata(path: Path) -> tuple[int, int, int, float, float]:
    capture = cv2.VideoCapture(str(path))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    capture.release()
    duration = frame_count / fps if fps > 0 else 0.0
    return width, height, frame_count, round(fps, 3), round(duration, 3)


def build_manifest() -> list[dict]:
    collected_at = datetime.now(timezone.utc).isoformat()
    scores = read_scores()
    records: list[dict] = []

    for position, (_, name, reference_class, note) in enumerate(REFERENCE_FILES, start=1):
        path = REFERENCE_DIR / name
        with Image.open(path) as image:
            width, height = image.size
        records.append(
            {
                "sample_id": f"asdu_ref_{position:02d}",
                "media_type": "image",
                "dataset_role": "reference_only",
                "reference_class": reference_class,
                "local_path": path.relative_to(OUT).as_posix(),
                "source_name": "user-provided article/social screenshot",
                "source_page": "https://mp.weixin.qq.com/s/2vqpHiJ6HmMgi2o_pF9i9g",
                "source_commit": "",
                "prompt_group": "",
                "image_model": "unknown",
                "talker_method": "unknown",
                "source_mos_0_5": "",
                "license": "unknown; do not redistribute",
                "redistribution": "no",
                "adult_appearance_review": "reference_only_or_mixed",
                "target_style_review_0_3": "",
                "width": width,
                "height": height,
                "frame_count": 1,
                "fps": "",
                "duration_seconds": "",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "collected_at_utc": collected_at,
                "label_status": "reference_not_ground_truth",
                "notes": note,
            }
        )

    for position, name in enumerate(SELECTED_VIDEOS, start=1):
        path = DYNAMIC_DIR / name
        stem = path.stem.split("_")
        width, height, frame_count, fps, duration = video_metadata(path)
        records.append(
            {
                "sample_id": f"asdu_video_{position:02d}",
                "media_type": "video",
                "dataset_role": "target_candidate",
                "reference_class": "ai_short_drama_like_talking_face",
                "local_path": path.relative_to(OUT).as_posix(),
                "source_name": "THQA-NTIRE talking-head quality dataset",
                "source_page": DATASET_PAGE,
                "source_commit": DATASET_COMMIT,
                "prompt_group": stem[0],
                "image_model": stem[1],
                "talker_method": stem[-1],
                "source_mos_0_5": scores[name],
                "license": DATASET_LICENSE,
                "redistribution": "review_before_release",
                "adult_appearance_review": "pass_visual_review",
                "target_style_review_0_3": 3,
                "width": width,
                "height": height,
                "frame_count": frame_count,
                "fps": fps,
                "duration_seconds": duration,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "collected_at_utc": collected_at,
                "label_status": "candidate_needs_human_uncanny_rating",
                "notes": "成人外观、写实AI女性说话脸；保留用于标注塑料感、空洞眼神、表情僵硬、口型不同步和身份漂移。",
            }
        )
    return records


def write_tables(records: list[dict]) -> None:
    fieldnames = list(records[0].keys())
    with (OUT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    with (OUT / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    label_fields = [
        "sample_id",
        "media_type",
        "ai_short_drama_face_relevance_0_3",
        "overall_uncanny_1_7",
        "template_face_similarity_1_7",
        "skin_plasticity_1_7",
        "gaze_vacancy_1_7",
        "expression_rigidity_1_7",
        "eye_mouth_incongruence_1_7",
        "microexpression_absence_1_7",
        "lip_sync_error_1_7",
        "temporal_identity_drift_1_7",
        "artifact_tags",
        "reviewer_notes",
    ]
    with (OUT / "annotation_template.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=label_fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "sample_id": record["sample_id"],
                    "media_type": record["media_type"],
                    "ai_short_drama_face_relevance_0_3": record["target_style_review_0_3"],
                }
            )


def video_frames(path: Path) -> list[Image.Image]:
    capture = cv2.VideoCapture(str(path))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    frames: list[Image.Image] = []
    for fraction in (0.2, 0.5, 0.8):
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, round((frame_count - 1) * fraction)))
        ok, frame = capture.read()
        if ok:
            frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    capture.release()
    return frames


def make_reference_sheet() -> None:
    tile_width, tile_height = 460, 340
    sheet = Image.new("RGB", (tile_width * 2, tile_height * 2), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (_, name, reference_class, _) in enumerate(REFERENCE_FILES):
        with Image.open(REFERENCE_DIR / name) as source:
            image = ImageOps.contain(source.convert("RGB"), (tile_width - 8, tile_height - 32))
        x = (index % 2) * tile_width + (tile_width - image.width) // 2
        y = (index // 2) * tile_height + 4
        sheet.paste(image, (x, y))
        draw.text(
            ((index % 2) * tile_width + 6, (index // 2) * tile_height + tile_height - 24),
            reference_class,
            fill="black",
        )
    sheet.save(PREVIEW_DIR / "reference_contact_sheet.jpg", quality=90)


def make_dynamic_sheet(records: list[dict]) -> None:
    video_records = [record for record in records if record["media_type"] == "video"]
    tile_width, tile_height, label_width = 224, 224, 180
    sheet = Image.new(
        "RGB",
        (label_width + tile_width * 3, tile_height * len(video_records)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for row_index, record in enumerate(video_records):
        path = OUT / record["local_path"]
        label = (
            f"{record['sample_id']}\n{record['image_model']} + {record['talker_method']}\n"
            f"MOS {record['source_mos_0_5']}"
        )
        draw.multiline_text((8, row_index * tile_height + 78), label, fill="black", spacing=4)
        for column_index, frame in enumerate(video_frames(path)):
            tile = ImageOps.fit(
                frame.convert("RGB"),
                (tile_width - 4, tile_height - 4),
                method=Image.Resampling.LANCZOS,
            )
            sheet.paste(
                tile,
                (label_width + column_index * tile_width + 2, row_index * tile_height + 2),
            )
    sheet.save(PREVIEW_DIR / "target_video_contact_sheet.jpg", quality=90)


def main() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    copy_inputs()
    records = build_manifest()
    write_tables(records)
    make_reference_sheet()
    make_dynamic_sheet(records)
    print(f"ready: {len(records)} records ({len(SELECTED_VIDEOS)} target videos) in {OUT}")


if __name__ == "__main__":
    main()
