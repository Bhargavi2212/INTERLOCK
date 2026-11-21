"""Model box -> page-normalised displayed-frame box [x0, y0, x1, y1] (no model import).

The model's box format (axis order and scale) is a setting, reading.yaml
drawing.box_format, set once by calibration on ESP Unit-1 waste water transfer
pumps (PHASE_3 Amendment B8), never on a set B item.
"""

from __future__ import annotations


def to_page(box, fmt: dict, crop: list[float]) -> list[float] | None:
    if not box or len(box) != 4:
        return None
    a, b, c, d = (float(v) / float(fmt["scale"]) for v in box)
    x0, y0, x1, y1 = (b, a, d, c) if fmt["order"] == "yx" else (a, b, c, d)
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    out = [crop[0] + min(x0, x1) * cw, crop[1] + min(y0, y1) * ch,
           crop[0] + max(x0, x1) * cw, crop[1] + max(y0, y1) * ch]
    return [round(v, 5) for v in out]


def centre(box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def iou(a, b) -> float:
    """Intersection over union of two [x0, y0, x1, y1] boxes."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def distance(a, b) -> float:
    (ax, ay), (bx, by) = centre(a), centre(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
