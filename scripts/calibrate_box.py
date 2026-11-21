"""Calibrate the model's box format ONCE on ESP Unit-1 waste water transfer pumps
(Part3 p.146; not a set B item). Bhargavi runs this (needs the key):

    python scripts/calibrate_box.py --plant <plant_id>

One vision call on the crop around the ESP Unit-1 label. Prints the model's raw
label box, the text-layer label box, and the page box under each candidate format
with its centre distance. Stop rule (PHASE_3 plan, approved): if the best format is
more than 0.01 of the page from the text-layer centre, STOP: set nothing, do not run
set B, show the raw output to Bhargavi.
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.drawing.boxes import distance, to_page  # noqa: E402
from app.drawing.locate import crop_png, crop_window, find_anchor  # noqa: E402
from app.drawing.vision import _prompt  # noqa: E402
from app.reading import schemas  # noqa: E402
from app.reading.models import get_models  # noqa: E402
from app.store.base import get_store  # noqa: E402

ITEM = {"item": "ESP Unit-1 waste water transfer pumps",
        "names": ["ESP Unit-1 waste water transfer pumps", "ESP waste water transfer pumps"], "unit_tag": "Unit-1"}
FILE, PAGE = "Part3.pdf", 146
FORMATS = [{"order": "yx", "scale": 1000}, {"order": "xy", "scale": 1000},
           {"order": "yx", "scale": 1}, {"order": "xy", "scale": 1}]
STOP_AT = 0.01


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plant", required=True)
    args = ap.parse_args()
    store = get_store()
    pages = store.get_pages_all(args.plant)
    p = next((x for x in pages if Path(x["file"]).name == FILE and x["page"] == PAGE), None)
    if p is None:
        print(f"{FILE} p.{PAGE} not in plant {args.plant}")
        return 1
    rec, png = store.get_page(args.plant, p["n"]), store.get_page_png(args.plant, p["n"])
    anchor = find_anchor(rec["words"], ITEM["names"], ITEM["unit_tag"])
    if anchor is None:
        print("no text-layer anchor for ESP Unit-1 (re-ingest the plant first?)")
        return 1
    window = crop_window(anchor["box"])
    out = get_models().see("drawing", _prompt(ITEM, FORMATS[0]), crop_png(png, window), schemas.DRAWING)
    raw = out.get("label_box")
    print("text-layer label:", anchor["text"], [round(v, 4) for v in anchor["box"]])
    print("crop window:", [round(v, 4) for v in window])
    print("model raw label_box:", raw, "| found:", out.get("found"), "| why:", out.get("why"))
    best = None
    for fmt in FORMATS:
        box = to_page(raw, fmt, window)
        dist = distance(box, anchor["box"]) if box else None
        print(f"  {fmt}: {box}  distance {None if dist is None else round(dist, 4)}")
        if dist is not None and (best is None or dist < best[1]):
            best = (fmt, dist)
    result = {"raw": out, "anchor": anchor["box"], "window": window,
              "best": best and {"format": best[0], "distance": best[1]}}
    (ROOT / "eval" / "results" / "calibration_esp_unit1.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    if best is None or best[1] > STOP_AT:
        print(f"\nSTOP: best distance {None if best is None else round(best[1], 4)} > {STOP_AT}. "
              "Set no format, do not run set B. Show this output to Bhargavi.")
        return 2
    print(f"\nOK: set reading.yaml drawing.box_format to {best[0]} (distance {round(best[1], 4)} <= {STOP_AT})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
