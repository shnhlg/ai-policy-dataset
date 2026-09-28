"""Remove known anti-bot landing pages from pre-merge collection batches."""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
MARKERS = ("validate.perfdrive.com", "shieldsquare", "captcha", "access denied", "unusual traffic", "enable javascript to continue", "security check")

for path in OUT.glob("oecd_linked_verified*.csv"):
    with path.open(encoding="utf-8-sig", newline="") as h:
        rows = list(csv.DictReader(h)); fields = h.seek(0) or (csv.DictReader(h).fieldnames or [])
    good = [r for r in rows if not any(m in (r.get("official_url_final", "") + " " + r.get("content_summary_original", "")).lower() for m in MARKERS)]
    if len(good) != len(rows):
        with path.open("w", encoding="utf-8-sig", newline="") as h:
            writer = csv.DictWriter(h, fieldnames=fields); writer.writeheader(); writer.writerows(good)
        print(f"{path.name}: removed {len(rows)-len(good)} block pages")
