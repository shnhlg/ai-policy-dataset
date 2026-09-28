from __future__ import annotations

import json
from pathlib import Path

import screen_thqa_ntire_candidates as base


ROOT = Path(__file__).resolve().parents[1]
base.OUT = ROOT / "data" / "raw" / "ai_short_drama_uncanny_mini" / "appearance_screening"
base.VIDEO_DIR = base.OUT / "videos"
base.PREVIEW_DIR = base.OUT / "previews"


def choose_appearance_candidates(rows: list[dict]) -> list[dict]:
    """One talking-head sample per portrait model for youthful prompt groups.

    The four prompt groups are intentionally screened rather than assumed adult.
    Prompt/model outputs that look under 18 are excluded after contact-sheet review.
    """

    chosen: list[dict] = []
    for prompt_id in ("2", "8", "9", "14"):
        matching = [row for row in rows if row["Video"].startswith(f"{prompt_id}_")]
        models = sorted(
            {
                Path(row["Video"]).stem.split("_")[1]
                for row in matching
                if Path(row["Video"]).stem.split("_")[1] != "voice"
            }
        )
        for model in models:
            model_rows = [
                row
                for row in matching
                if Path(row["Video"]).stem.split("_")[1] == model
            ]
            preferred = []
            for method in ("dreamtalk", "wavlip", "musetalk", "audio2head"):
                preferred = [
                    row
                    for row in model_rows
                    if Path(row["Video"]).stem.split("_")[-1] == method
                ]
                if preferred:
                    break
            if not preferred:
                continue
            chosen.append(
                min(
                    preferred,
                    key=lambda row: (abs(float(row["Score"]) - 2.5), row["Video"]),
                )
            )
    return chosen


def main() -> None:
    base.OUT.mkdir(parents=True, exist_ok=True)
    rows = base.fetch_csv_rows()
    candidates = choose_appearance_candidates(rows)
    base.extract_candidates(candidates)
    base.write_screening_manifest(candidates)
    base.make_contact_sheet(candidates)
    print(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "source": base.DATASET,
                "commit": base.COMMIT,
                "purpose": "adult-appearance and target-style screening",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
