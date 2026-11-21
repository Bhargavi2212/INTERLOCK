"""Step 0: uploaded PDFs -> pages. No model.

Per page: text, word positions normalised 0-1, is_drawing, PNG for drawing
pages only. Writes plants/{id}/pages/{n}.json (+ .png) and pages_all.json
(every page {n, file, page, text} in n order; the pipeline's one read).
n continues across batches: files of a new batch, in sorted relative-path
order, follow the pages already ingested.
"""

from __future__ import annotations

import os
import tempfile

import pymupdf

from app.reading.settings import reading_settings
from app.store.base import Store

PT_PER_INCH = 72
MM_PER_INCH = 25.4


def is_drawing(page, text: str, cfg: dict) -> bool:
    long_side_mm = max(page.rect.width, page.rect.height) / PT_PER_INCH * MM_PER_INCH
    return long_side_mm > cfg["drawing_min_long_side_mm"] or len(text.strip()) < cfg["drawing_max_text_chars"]


def page_record(page, file: str, page_no: int, n: int, cfg: dict) -> tuple[dict, bool]:
    text = page.get_text("text")
    w, h = page.rect.width, page.rect.height
    words = [[round(x0 / w, 5), round(y0 / h, 5), round(x1 / w, 5), round(y1 / h, 5), t]
             for x0, y0, x1, y1, t, *_ in page.get_text("words")]
    drawing = is_drawing(page, text, cfg)
    return ({"n": n, "file": file, "page": page_no, "text": text, "width": w, "height": h,
             "is_drawing": drawing, "words": words}, drawing)


def ingest_plant(store: Store, plant_id: str, job_id: str) -> dict:
    cfg = reading_settings()["ingest"]
    plant = store.get_plant(plant_id)
    pending = sorted((f for f in plant["files"] if f["status"] == "uploading"),
                     key=lambda f: f["relative_path"])

    # Files whose upload never arrived are marked missing, not silently dropped.
    ready = []
    for f in pending:
        if store.file_exists(plant_id, f["relative_path"]):
            ready.append(f["relative_path"])
        else:
            _set_file(store, plant_id, f["relative_path"], status="missing")

    store.mutate_plant(plant_id, lambda d: d.update(ingest_status="running"))
    pages_all = store.get_pages_all(plant_id) if plant.get("page_count") else []
    n = len(pages_all)
    pages_done = 0
    files_done = 0
    store.update_job(job_id, {"step": "ingest", "progress": {"files_done": 0, "files_total": len(ready),
                                                             "pages_done": 0}})
    for rel in ready:
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            store.download_file(plant_id, rel, tmp)
            count = 0
            with pymupdf.open(tmp) as doc:
                for i, page in enumerate(doc, start=1):
                    rec, drawing = page_record(page, rel, i, n, cfg)
                    store.put_page(plant_id, n, rec)
                    if drawing:
                        store.put_page_png(plant_id, n, page.get_pixmap(dpi=cfg["png_dpi"]).tobytes("png"))
                    pages_all.append({"n": n, "file": rel, "page": i, "text": rec["text"]})
                    n += 1
                    count += 1
                    pages_done += 1
                    if pages_done % cfg["progress_every_pages"] == 0:
                        store.update_job(job_id, {"progress": {"files_done": files_done,
                                                               "files_total": len(ready),
                                                               "pages_done": pages_done}})
            _set_file(store, plant_id, rel, status="ingested", pages=count)
        except Exception as e:  # a broken PDF fails that file, not the job
            _set_file(store, plant_id, rel, status="failed", error=type(e).__name__)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        files_done += 1
        store.update_job(job_id, {"progress": {"files_done": files_done, "files_total": len(ready),
                                               "pages_done": pages_done}})

    store.put_pages_all(plant_id, pages_all)
    chars = sum(len(p["text"]) for p in pages_all)
    est = reading_settings()["long_read"]["chars_per_token_estimate"]

    def finish(d):
        d.update(page_count=len(pages_all), ingest_status="done",
                 token_count={"value": chars // est, "estimated": True})

    plant = store.mutate_plant(plant_id, finish)
    return {"page_count": plant["page_count"], "pages_this_batch": pages_done,
            "files": {f["relative_path"]: f["status"] for f in plant["files"]}}


def _set_file(store: Store, plant_id: str, rel: str, **fields) -> None:
    def fn(d):
        for f in d["files"]:
            if f["relative_path"] == rel:
                f.update(fields)

    store.mutate_plant(plant_id, fn)
