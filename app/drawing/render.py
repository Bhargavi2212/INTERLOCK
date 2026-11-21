"""Red box and values drawn on the drawing crop (PyMuPDF only; no new library)."""

from __future__ import annotations

import pymupdf

RED = (0.85, 0.1, 0.1)
GREY = (0.5, 0.5, 0.5)


def _to_crop(box, crop, w, h) -> pymupdf.Rect | None:
    if not box:
        return None
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    return pymupdf.Rect((box[0] - crop[0]) / cw * w, (box[1] - crop[1]) / ch * h,
                        (box[2] - crop[0]) / cw * w, (box[3] - crop[1]) / ch * h)


def draw(crop_png: bytes, drawing: dict) -> bytes:
    """item box: thick red (thin grey if not verified); readings: thin red if verified,
    grey dashed if not, with the value written beside."""
    with pymupdf.open(stream=crop_png, filetype="png") as img:
        w, h = img[0].rect.width, img[0].rect.height
        doc = pymupdf.open()
        page = doc.new_page(width=w, height=h)
        page.insert_image(page.rect, stream=crop_png)
        crop = drawing.get("crop_box") or [0, 0, 1, 1]
        size = max(10.0, min(w, h) / 60)
        item = _to_crop(drawing.get("item_box"), crop, w, h)
        if item:
            page.draw_rect(item, color=RED if drawing.get("verified") else GREY, width=size / 2.5)
        # one box per printed label (line size, shared header and role often share "200NB"),
        # one caption per box: no overprinted text
        groups: dict[tuple, list] = {}
        for r in drawing.get("readings", []):
            if r.get("box"):
                groups.setdefault(tuple(round(v, 4) for v in r["box"]), []).append(r)
        for box, rs in groups.items():
            rect = _to_crop(list(box), crop, w, h)
            ok = all(r.get("evidence_ok") for r in rs)
            page.draw_rect(rect, color=RED if ok else GREY, width=size / 5, dashes=None if ok else "[4] 0")
            text = "; ".join(f"{r.get('input')} {r.get('value')} {r.get('unit') or ''}".strip() for r in rs)
            y = rect.y0 - size * 0.4 if rect.y0 > size * 1.5 else rect.y1 + size
            page.insert_text((max(rect.x0, 2), y), text, fontsize=size * 0.8, color=RED if ok else GREY)
        out = page.get_pixmap().tobytes("png")
        doc.close()
        return out
