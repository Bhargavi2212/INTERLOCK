"""The drawing evidence rule (no model). A value read from a P&ID reaches the rules
only if code confirms it against the PDF's own text layer:

1. the box is on the page (inside 0-1, positive area);
2. the text-layer words whose centres fall inside the box (expanded by box_margin)
   contain label_text (normalised, spaces ignored);
3. the value is in label_text and its unit is known (as evidence.py);
4. the item box contains the item's printed label, including the unit-tag token,
   else found is overridden to false (stops a confident wrong box / a look-alike);
5. shared_discharge: checks 1-2 on the header's size label; the topology itself is
   the model's reading of the picture, stated as an assumption.
A page with no text layer: nothing is verifiable, nothing reaches the rules.
"""

from __future__ import annotations

from app.drawing.boxes import distance
from app.drawing.locate import _below, box_of, find_anchor, segments, tokens
from app.reading.evidence import unit_known, value_in_quote
from app.reading.search import squash
from app.reading.settings import reading_settings

TEXT_INPUTS = {"line_role", "shared_discharge"}


def on_page(box) -> bool:
    return (box is not None and len(box) == 4 and all(0.0 <= v <= 1.0 for v in box)
            and box[2] > box[0] and box[3] > box[1])


def words_in(words: list, box, margin: float | None = None) -> list:
    m = reading_settings()["drawing"]["box_margin"] if margin is None else margin
    x0, y0, x1, y1 = box[0] - m, box[1] - m, box[2] + m, box[3] + m
    inside = [w for w in words if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
    return sorted(inside, key=lambda w: (round((w[1] + w[3]) / 2, 3), w[0]))


def label_in_box(words: list, box, label_text: str) -> bool:
    return bool(squash(label_text)) and squash(label_text) in squash(" ".join(w[4] for w in words_in(words, box)))


def check_item(words: list, item_box, label_box, understanding: dict) -> tuple[bool, str]:
    if not words:
        return False, "not verifiable (no text layer)"
    for name, box in (("item box", item_box), ("label box", label_box)):
        if not on_page(box):
            return False, f"{name} is not on the page"
    names = understanding.get("names", []) + [understanding.get("item", "")]
    inside = find_anchor(words_in(words, item_box), names, understanding.get("unit_tag", ""))
    if inside is None or not inside["unit_words"]:
        return False, "box does not contain the item's label (with its unit tag)"
    return True, f"item label '{inside['text']}' found in the box"


def check_reading(r: dict, words: list, file: str, page: int) -> dict:
    out = {"input": r.get("input"), "value": r.get("value"), "unit": r.get("unit", "") or "",
           "file": file, "page": page, "quote": r.get("label_text", ""),
           "box": tuple(r["box"]) if r.get("box") else None, "role": r.get("role"),
           "source": "drawing"}
    reason = ""
    if not words:
        reason = "not verifiable (no text layer)"
    elif not on_page(r.get("box")):
        reason = "box is not on the page"
    elif not label_in_box(words, r["box"], r.get("label_text", "")):
        reason = f"label '{r.get('label_text')}' is not inside the box in the text layer"
    elif r.get("input") not in TEXT_INPUTS:
        if not value_in_quote(r.get("value"), r.get("label_text", ""), r.get("input", "")):
            reason = f"value '{r.get('value')}' is not in the label"
        else:
            ok, why = unit_known(r.get("input", ""), r.get("value"), out["unit"])
            reason = "" if ok else f"unit '{out['unit']}' not usable: {why}"
    out["evidence_ok"] = not reason
    out["evidence_reason"] = reason or "label verified in the text layer"
    if r.get("input") == "shared_discharge" and not reason and str(r.get("value")).strip().lower() in ("true", "yes"):
        out["assumption"] = (f"pumps share one header: read from the drawing by Argon; header label "
                             f"'{r.get('label_text')}' verified in the text layer at {file} p.{page}")
    return out


def line_role_values(readings: list[dict]) -> list[dict]:
    """A verified line-size reading with a role also gives a line_role value (same box, same label)."""
    out = []
    for r in readings:
        if r["input"] == "line_nb" and r["evidence_ok"] and r.get("role"):
            out.append({**r, "input": "line_role", "value": r["role"], "unit": ""})
    return out


LINE_INPUTS = ("line_nb", "line_role", "shared_discharge")


def pump_labels(words: list, anchor: dict | None) -> list[tuple[str, list]]:
    """Printed text runs containing 'PUMP' (abbreviations applied), except this item's own label."""
    own = {tuple(w) for w in (anchor or {}).get("words", [])}
    segs = segments(words)
    out = []
    for seg in segs:
        if "pump" not in tokens(" ".join(w[4] for w in seg)) or all(tuple(w) in own for w in seg):
            continue
        above = next((a for a in segs if a is not seg and _below(a, seg)), None)   # label's first line
        label = (above or []) + seg
        if all(tuple(w) in own for w in label):
            continue
        out.append((" ".join(w[4] for w in label), box_of(label)))
    return out


def check_line_near_item(readings: list[dict], words: list, anchor: dict | None) -> list[dict]:
    """A line reading passes only if its label's centre is nearer to this item's printed label
    than to any other pump label on the sheet (Bhargavi, 21 Nov: stops a look-alike's line)."""
    others = pump_labels(words, anchor)
    for r in readings:
        if r.get("input") not in LINE_INPUTS or not r.get("evidence_ok"):
            continue
        if anchor is None:
            r["evidence_ok"] = False
            r["evidence_reason"] = "no text-layer label for the item to measure the line against"
            continue
        mine = distance(r["box"], anchor["box"])
        nearest = min(others, key=lambda o: distance(r["box"], o[1]), default=None)
        if nearest is not None and distance(r["box"], nearest[1]) <= mine:
            r["evidence_ok"] = False
            r["evidence_reason"] = (f"line label is nearer to another pump label ('{nearest[0]}') "
                                    f"than to this item's ('{anchor['text']}')")
            r.pop("assumption", None)
        else:
            r["evidence_reason"] += f"; nearest pump label is this item's ({mine:.3f} of the page)"
    return readings
