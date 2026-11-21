"""Step 6: Argon looks at the P&ID (image) and boxes the item; code verifies every box.

Box format: Argon returns boxes in the format set by reading.yaml drawing.box_format.
CALIBRATION (PHASE_3 Amendment B8): set once from scripts/calibrate_box.py on ESP
Unit-1 waste water transfer pumps (Part3 p.146; never a set B item).
  Result (21 Nov, Bhargavi confirmed): {order: yx, scale: 1000}, i.e. [ymin, xmin, ymax, xmax] 0-1000.
  Text-layer label [0.4214, 0.6040, 0.4541, 0.6123]; model raw [489, 459, 535, 539] in crop
  [0.2377, 0.4081, 0.6377, 0.8081]. Centre distance 0.0048 for both yx and xy (a near-centre box
  in a square crop cannot separate axis order); IoU yx 0.44 vs xy 0.22; yx matches the label's
  left edge, top edge and width (0.032 vs 0.033), xy turns the wide label tall. Raw output:
  eval/results/calibration_esp_unit1.json.

Flow per drawing page: text-layer anchor -> crop (0.40 of the page around it, or the
whole page) -> Argon -> boxes to page coordinates -> verify (code). No whole-sheet
fallback: no line size in the crop -> R1 held, and the step note says so.
"""

from __future__ import annotations

from app.drawing import render
from app.drawing.boxes import to_page
from app.drawing.locate import crop_png, crop_window, drawing_pages, find_anchor
from app.drawing.verify import check_item, check_line_near_item, check_reading, line_role_values
from app.reading import schemas
from app.reading.settings import reading_settings

PROMPT = """This image is part of a P&ID drawing from a process plant.

Find: {item} (also printed as: {names}). Unit / train: {unit_tag}.
Box ONLY this item, not a similar item for another unit or system. If it is not on the image, set
found=false and give no boxes.
- item_box: the pump symbols of this item together with their printed label.
- label_box: the printed label text of this item only.
- readings (each with label_text copied exactly as printed on the drawing, and the box of that printed text):
  * line_nb: the size label of the line these pumps discharge into (e.g. "200NB"), value "200", unit "NB",
    role "pump discharge", "discharge header" or "pump suction".
  * shared_discharge: value "true" if these pumps discharge into one common line/header, "false" if separate;
    its label_text and box are the size label of that line.
  * flow_per_pump and arrangement if printed in the item's label (e.g. "105M3/HR (2W)").
Boxes are [{order_hint}] scaled 0-{scale} relative to this image.
why: one sentence.
"""


def _prompt(u: dict, fmt: dict) -> str:
    order_hint = "ymin, xmin, ymax, xmax" if fmt["order"] == "yx" else "xmin, ymin, xmax, ymax"
    return PROMPT.format(item=u.get("item"), names=", ".join(u.get("names", [])[:8]),
                         unit_tag=u.get("unit_tag") or "none", order_hint=order_hint, scale=fmt["scale"])


def _converted(out: dict, fmt: dict, window: list[float]) -> dict:
    return {
        "found": bool(out.get("found")),
        "item_box": to_page(out.get("item_box"), fmt, window),
        "label_box": to_page(out.get("label_box"), fmt, window),
        "readings": [{**r, "box": to_page(r.get("box"), fmt, window)} for r in out.get("readings", [])],
        "why": out.get("why", ""),
    }


def look_on_page(models, u: dict, page_rec: dict, page_png: bytes) -> dict:
    cfg = reading_settings()["drawing"]
    fmt = cfg["box_format"]
    words = page_rec.get("words") or []
    anchor = find_anchor(words, u.get("names", []) + [u.get("item", "")], u.get("unit_tag", ""))
    window = crop_window(anchor["box"] if anchor else None)
    crop = crop_png(page_png, window)
    seen = _converted(models.see("drawing", _prompt(u, fmt), crop, schemas.DRAWING, cfg.get("thinking", "low")),
                      fmt, window)
    # No whole-sheet fallback (Bhargavi, 21 Nov): a line not in the crop around the item's own
    # label is not trusted; R1 stays held and the step says so.
    file, page = page_rec["file"], page_rec["page"]

    if seen["found"]:
        ok, why = check_item(words, seen["item_box"], seen["label_box"], u)
    else:
        ok, why = False, "the model did not find the item on this sheet"
    readings = check_line_near_item([check_reading(r, words, file, page) for r in seen["readings"]], words, anchor)
    if not ok:
        for r in readings:
            r["evidence_ok"] = False
            r["evidence_reason"] = f"item not verified ({why})"
    readings += line_role_values(readings)
    have_line = any(r["input"] == "line_nb" and r["evidence_ok"] for r in readings)
    note = "" if have_line else "no line size in the crop around the item's label: R1 held"
    return {"note": note,"file": file, "page": page, "n": page_rec["n"], "found": ok, "model_found": seen["found"],
            "anchor": "text layer" if anchor else "none", "anchor_text": anchor["text"] if anchor else None,
            "item_box": seen["item_box"], "label_box": seen["label_box"], "crop_box": window,
            "readings": readings, "verified": ok, "why": seen["why"], "check": why, "_crop": crop}


def run_drawing(store, models, plant_id: str, u: dict, kept: list[dict], pages_all: list[dict]) -> dict:
    """The drawing for this change: first verified drawing page, else the first one tried."""
    pages = drawing_pages(kept, pages_all, u.get("names", []) + [u.get("item", "")])
    if not pages:
        return {"found": False, "reason": "no drawing page among the pages found", "readings": []}
    first = None
    for p in pages:
        rec = store.get_page(plant_id, p["n"])
        png = store.get_page_png(plant_id, p["n"])
        if rec is None or png is None:
            continue
        res = look_on_page(models, u, rec, png)
        first = first or res
        if res["found"]:
            first = res
            break
    if first is None:
        return {"found": False, "reason": "drawing page image not available", "readings": []}
    first["png"] = render.draw(first.pop("_crop"), first)
    return first
