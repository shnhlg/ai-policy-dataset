from __future__ import annotations

import csv
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "china_ai_short_drama_mini"
VIDEO_DIR = OUT / "research_only_videos"
PREVIEW_DIR = OUT / "previews"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


SOURCES = [
    {
        "sample_id": "caisd_xingan_ep01",
        "work": "兴安岭诡事",
        "episode": "第1集",
        "bvid": "BV18EnAz8EdK",
        "cid": "32552780292",
        "page": "https://www.bilibili.com/bangumi/play/ep2194402",
        "api": "pgc",
        "source_tier": "commercial_ai_live_action_short_drama",
        "notes": "B站剧集页公开免费集；纯AIGC奇幻探险短剧。",
    },
    {
        "sample_id": "caisd_xingan_ep02",
        "work": "兴安岭诡事",
        "episode": "第2集",
        "bvid": "BV18EnAz8EqL",
        "cid": "32552780404",
        "page": "https://www.bilibili.com/bangumi/play/ep2194401",
        "api": "pgc",
        "source_tier": "commercial_ai_live_action_short_drama",
        "notes": "B站剧集页公开免费集；纯AIGC奇幻探险短剧。",
    },
    {
        "sample_id": "caisd_xingan_ep03",
        "work": "兴安岭诡事",
        "episode": "第3集",
        "bvid": "BV1uJnAzfEHv",
        "cid": "32552780154",
        "page": "https://www.bilibili.com/bangumi/play/ep2194400",
        "api": "pgc",
        "source_tier": "commercial_ai_live_action_short_drama",
        "notes": "B站剧集页公开免费集；纯AIGC奇幻探险短剧。",
    },
    {
        "sample_id": "caisd_xingan_ep04",
        "work": "兴安岭诡事",
        "episode": "第4集",
        "bvid": "BV1uEnAz8E13",
        "cid": "32552780496",
        "page": "https://www.bilibili.com/bangumi/play/ep2194399",
        "api": "pgc",
        "source_tier": "commercial_ai_live_action_short_drama",
        "notes": "B站剧集页公开免费集；纯AIGC奇幻探险短剧。",
    },
    {
        "sample_id": "caisd_shanhai_trailer",
        "work": "山海奇镜之劈波斩浪",
        "episode": "预告片",
        "bvid": "BV1Yf421q7My",
        "cid": "1606005117",
        "page": "https://www.bilibili.com/video/BV1Yf421q7My/",
        "api": "ugc",
        "source_tier": "institutional_aigc_short_drama",
        "notes": "原创投稿；可灵AI支持的中国AIGC奇幻短剧预告。",
    },
    {
        "sample_id": "caisd_sanxingdui_ep01",
        "work": "三星堆：未来启示录",
        "episode": "第1集",
        "bvid": "BV1gZabezETH",
        "cid": "500001609207276",
        "page": "https://www.bilibili.com/video/BV1gZabezETH/",
        "api": "ugc",
        "source_tier": "institutional_aigc_short_drama",
        "notes": "博纳影业AIGMS制作中心原创投稿；连续叙事AIGC科幻短剧。",
    },
    {
        "sample_id": "caisd_newworld_trailer",
        "work": "新世界加载中",
        "episode": "先导片",
        "bvid": "BV1XjPyeyE3J",
        "cid": "28226617386",
        "page": "https://www.bilibili.com/video/BV1XjPyeyE3J/",
        "api": "ugc",
        "source_tier": "institutional_ai_series",
        "notes": "异类Outliers原创投稿；AI单元剧集先导片。",
    },
    {
        "sample_id": "caisd_qiannian_full",
        "work": "千年迷梦",
        "episode": "完整短片",
        "bvid": "BV1e34ReMEi2",
        "cid": "25879119529",
        "page": "https://www.bilibili.com/video/BV1e34ReMEi2/",
        "api": "ugc",
        "source_tier": "independent_ai_short_drama",
        "notes": "个人创作者原创投稿；全AI制作仙侠短剧。",
    },
]


DISCOVERY_ONLY = [
    {
        "work": "奶团太后宫心计",
        "platform": "抖音",
        "account_or_producer": "爱微剧场 / 可梦AI",
        "genre": "古装宫廷、重生逆袭、AI仿真人",
        "priority": "A",
        "source_url": "https://www.douyin.com/search/奶团太后宫心计?type=video",
        "acquisition_status": "source_only_login_required",
        "notes": "最贴近用户参考中的量产AI短剧脸；应优先从官方账号申请研究授权。",
    },
    {
        "work": "我靠唱歌打脸全团",
        "platform": "抖音",
        "account_or_producer": "可梦AI",
        "genre": "年代、AI仿真人",
        "priority": "A",
        "source_url": "https://www.douyin.com/search/我靠唱歌打脸全团?type=video",
        "acquisition_status": "source_only_login_required",
        "notes": "真人AI年代短剧，适合补充非古装题材。",
    },
    {
        "work": "九尾狐男妖爱上我",
        "platform": "抖音",
        "account_or_producer": "待核验",
        "genre": "玄幻、AI仿真人",
        "priority": "A",
        "source_url": "https://www.douyin.com/search/九尾狐男妖爱上我?type=video",
        "acquisition_status": "source_only_login_required",
        "notes": "公开报道中的高播放AI仿真人短剧；需核验官方首发账号。",
    },
    {
        "work": "斩仙台AI真人版",
        "platform": "红果短剧 / 抖音",
        "account_or_producer": "待核验",
        "genre": "仙侠、AI仿真人",
        "priority": "A",
        "source_url": "https://www.douyin.com/search/斩仙台AI真人版?type=video",
        "acquisition_status": "source_only_login_required",
        "notes": "2025年末AI真人短剧案例；不从非官方搬运页下载。",
    },
    {
        "work": "嫡女泣血，母亲掀翻帝王家",
        "platform": "抖音 / 短剧平台",
        "account_or_producer": "待核验",
        "genre": "古装、AI仿真人",
        "priority": "A",
        "source_url": "https://www.douyin.com/search/嫡女泣血母亲掀翻帝王家?type=video",
        "acquisition_status": "source_only_login_required",
        "notes": "2026年AI仿真人短剧案例；优先联系出品方。",
    },
]


def request_json(url: str, referer: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Referer": referer, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def ugc_metadata(source: dict) -> dict:
    data = request_json(
        f"https://api.bilibili.com/x/web-interface/view?bvid={source['bvid']}",
        source["page"],
    )["data"]
    return {
        "platform_title": data.get("title", ""),
        "uploader": (data.get("owner") or {}).get("name", ""),
        "platform_duration_seconds": data.get("duration", ""),
        "bilibili_copyright_flag": data.get("copyright", ""),
        "cover_url": data.get("pic", ""),
    }


def play_url(source: dict) -> str:
    params = urllib.parse.urlencode(
        {"bvid": source["bvid"], "cid": source["cid"], "qn": 16, "fnval": 0}
    )
    if source["api"] == "pgc":
        endpoint = f"https://api.bilibili.com/pgc/player/web/playurl?{params}"
    else:
        endpoint = f"https://api.bilibili.com/x/player/playurl?{params}"
    payload = request_json(endpoint, source["page"])
    data = payload.get("result") or payload.get("data") or {}
    durls = data.get("durl") or []
    if payload.get("code") != 0 or not durls:
        raise RuntimeError(f"No public low-resolution play URL for {source['sample_id']}: {payload}")
    return durls[0]["url"]


def download(url: str, destination: Path, referer: str, retries: int = 4) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Referer": referer},
            )
            with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
            os.replace(partial, destination)
            return
        except Exception as exc:  # noqa: BLE001
            error = exc
            partial.unlink(missing_ok=True)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to download {destination.name}") from error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def video_metadata(path: Path) -> tuple[int, int, int, float, float]:
    capture = cv2.VideoCapture(str(path))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    capture.release()
    return width, height, frames, round(fps, 3), round(frames / fps, 3) if fps else 0.0


def sample_frames(path: Path) -> list[Image.Image]:
    capture = cv2.VideoCapture(str(path))
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    result: list[Image.Image] = []
    for fraction in (0.2, 0.5, 0.8):
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, round((frames - 1) * fraction)))
        ok, frame = capture.read()
        if ok:
            result.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    capture.release()
    return result


def build_manifest() -> list[dict]:
    collected_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for source in SOURCES:
        print(f"collecting {source['sample_id']} ...", flush=True)
        metadata = ugc_metadata(source)
        url = play_url(source)
        path = VIDEO_DIR / f"{source['sample_id']}.mp4"
        download(url, path, source["page"])
        width, height, frame_count, fps, duration = video_metadata(path)
        rows.append(
            {
                "sample_id": source["sample_id"],
                "work": source["work"],
                "episode": source["episode"],
                "source_tier": source["source_tier"],
                "platform": "bilibili",
                "source_page": source["page"],
                "bvid": source["bvid"],
                "cid": source["cid"],
                **metadata,
                "download_quality": "qn=16 low-resolution public stream",
                "local_path": path.relative_to(OUT).as_posix(),
                "license": "copyright retained by uploader/producer",
                "redistribution": "no; private research copy only",
                "target_class": "china_ai_short_drama_candidate",
                "deepfake_or_face_swap": "no_evidence; full_scene_aigc_work",
                "age_review": "pending_frame_level_review",
                "width": width,
                "height": height,
                "frame_count": frame_count,
                "fps": fps,
                "duration_seconds": duration,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "collected_at_utc": collected_at,
                "notes": source["notes"],
            }
        )
    return rows


def write_tables(rows: list[dict]) -> None:
    with (OUT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with (OUT / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    with (OUT / "discovery_registry.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DISCOVERY_ONLY[0].keys()))
        writer.writeheader()
        writer.writerows(DISCOVERY_ONLY)

    label_fields = [
        "sample_id",
        "work",
        "is_full_scene_ai_short_drama_0_1",
        "is_ai_live_action_style_0_1",
        "overall_uncanny_1_7",
        "face_template_similarity_1_7",
        "skin_plasticity_1_7",
        "gaze_vacancy_1_7",
        "expression_rigidity_1_7",
        "lip_sync_error_1_7",
        "character_identity_drift_1_7",
        "body_motion_anomaly_1_7",
        "shot_continuity_error_1_7",
        "age_appearance",
        "artifact_tags",
        "reviewer_notes",
    ]
    with (OUT / "annotation_template.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=label_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "work": row["work"],
                    "is_full_scene_ai_short_drama_0_1": 1,
                }
            )


def make_contact_sheet(rows: list[dict]) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    label_width, tile_width, tile_height = 250, 256, 228
    sheet = Image.new(
        "RGB", (label_width + tile_width * 3, tile_height * len(rows)), "white"
    )
    draw = ImageDraw.Draw(sheet)
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    font = ImageFont.truetype(str(font_path), 16) if font_path.exists() else ImageFont.load_default()
    for index, row in enumerate(rows):
        label = f"{row['sample_id']}\n{row['work']} {row['episode']}\n{row['duration_seconds']}s"
        draw.multiline_text(
            (8, index * tile_height + 70),
            label,
            fill="black",
            spacing=5,
            font=font,
        )
        for frame_index, frame in enumerate(sample_frames(OUT / row["local_path"])):
            tile = ImageOps.fit(
                frame.convert("RGB"),
                (tile_width - 4, tile_height - 4),
                method=Image.Resampling.LANCZOS,
            )
            sheet.paste(
                tile,
                (label_width + frame_index * tile_width + 2, index * tile_height + 2),
            )
    sheet.save(PREVIEW_DIR / "china_ai_short_drama_contact_sheet.jpg", quality=90)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_manifest()
    write_tables(rows)
    make_contact_sheet(rows)
    print(json.dumps({"samples": len(rows), "output": str(OUT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
