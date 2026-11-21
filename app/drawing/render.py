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
        for r in drawing.get("readings", []):
            rect = _to_crop(r.get("box"), crop, w, h)
            if rect is None:
                continue
            ok = r.get("evidence_ok")
            page.draw_rect(rect, color=RED if ok else GREY, width=size / 6, dashes=None if ok else "[4] 0")
            text = f"{r.get('input')}: {r.get('value')} {r.get('unit') or ''}".strip()
            page.insert_text((rect.x1 + 4, max(rect.y0 + size, size)), text, fontsize=size, color=RED if ok else GREY)
        out = page.get_pixmap().tobytes("png")
        doc.close()
        return out
