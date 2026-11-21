"""FastAPI app: /health, the one screen, and the protected API (ARCHITECTURE.md section 6)."""

from __future__ import annotations

import logging
import posixpath
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api.access import require_access
from app.config import get_settings
from app.jobs import runner
from app.store.base import get_store

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
log = logging.getLogger("interlock.api")


@asynccontextmanager
async def lifespan(_app):
    try:
        n = runner.fail_unfinished_on_startup()
        if n:
            log.warning("marked %d unfinished jobs failed (server restarted)", n)
    except Exception as e:  # never block /health on a store problem
        log.warning("startup job sweep skipped: %s", type(e).__name__)
    yield


app = FastAPI(title="Interlock", lifespan=lifespan)
api = APIRouter(dependencies=[Depends(require_access)])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": get_settings().app_version}


NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    """The one screen. Static links carry the version, so a deploy is never served stale JS/CSS."""
    v = get_settings().app_version
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("/static/app.js", f"/static/app.js?v={v}").replace("/static/app.css", f"/static/app.css?v={v}")
    return HTMLResponse(html, headers=NO_CACHE)


# ---------------------------------------------------------------- plants and upload

class NewPlant(BaseModel):
    name: str


class FileIn(BaseModel):
    relative_path: str
    size: int
    content_hash: str
    content_type: str = ""


def _plant_or_404(plant_id: str) -> dict:
    plant = get_store().get_plant(plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail="plant not found")
    return plant


def clean_path(raw: str) -> str | None:
    """Relative path with '/' separators, or None if unsafe."""
    p = raw.replace("\\", "/").strip()
    if not p or p.startswith("/") or ":" in p.split("/")[0]:
        return None
    parts = p.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return posixpath.join(*parts)


@api.post("/plants")
def create_plant(body: NewPlant) -> dict:
    plant = get_store().create_plant(body.name.strip() or "plant")
    return {"plant_id": plant["plant_id"]}


@api.get("/plants/{plant_id}")
def get_plant(plant_id: str) -> dict:
    return _plant_or_404(plant_id)


@api.post("/plants/{plant_id}/files")
def add_files(plant_id: str, files: list[FileIn]) -> dict:
    plant = _plant_or_404(plant_id)
    store = get_store()
    known_hashes = {f["content_hash"] for f in plant["files"] if f.get("status") not in ("failed", "missing")}
    known_paths = {f["relative_path"] for f in plant["files"]}
    accepted, skipped, duplicates, new_entries = [], [], [], []

    for f in files:
        rel = clean_path(f.relative_path)
        if rel is None:
            skipped.append({"relative_path": f.relative_path, "reason": "unsafe path"})
            continue
        ext = posixpath.splitext(rel)[1].lower()
        if ext != ".pdf":
            skipped.append({"relative_path": rel, "reason": f"not a PDF: {ext or 'no extension'}"})
            continue
        if f.size <= 0:
            skipped.append({"relative_path": rel, "reason": "empty file"})
            continue
        if f.content_hash in known_hashes:
            duplicates.append({"relative_path": rel})
            continue
        if rel in known_paths:
            skipped.append({"relative_path": rel, "reason": "a different file with this path is already in the plant"})
            continue
        known_hashes.add(f.content_hash)
        known_paths.add(rel)
        new_entries.append({"relative_path": rel, "size": f.size, "content_hash": f.content_hash,
                            "status": "uploading", "pages": 0, "skipped_reason": None})
        accepted.append({"relative_path": rel, "upload_url": store.signed_put_url(plant_id, rel)})

    if new_entries:
        store.mutate_plant(plant_id, lambda d: d["files"].extend(new_entries))
    return {"accepted": accepted, "skipped": skipped, "duplicates": duplicates}


@api.post("/plants/{plant_id}/ingest")
def ingest(plant_id: str) -> dict:
    _plant_or_404(plant_id)
    from app.ingest.ingest import ingest_plant

    store = get_store()
    job_id = store.create_job({"type": "ingest", "plant_id": plant_id, "step": "queued",
                               "progress": {"files_done": 0, "files_total": 0, "pages_done": 0}})
    runner.submit(job_id, lambda: ingest_plant(store, plant_id, job_id))
    return {"job_id": job_id}


class ChangeIn(BaseModel):
    text: str


def run_change_job(store, plant_id: str, change_id: str, text: str, job_id: str) -> dict:
    """Steps 1-9 as a background job; the result is stored under the change id."""
    from app.explain.carbon import explain
    from app.explain.headlines import headlines
    from app.reading.models import get_models
    from app.reading.pipeline import check_change

    models = get_models()

    def progress(steps, name):
        store.update_job(job_id, {"step": name, "steps": list(steps)})

    res = check_change(store, models, plant_id, change_id, text, progress=progress,
                       explain_fn=lambda dis, values: explain(models, text, dis, values),
                       headlines_fn=lambda after, dis, clashes: headlines(models, after, dis, clashes))
    store.put_change(plant_id, change_id, res)
    store.update_job(job_id, {"step": "done", "steps": res["steps"]})
    return {"change_id": change_id, "verdict": res["verdict"]["verdict"], "seconds_total": res["seconds_total"]}


@api.post("/plants/{plant_id}/changes")
def check_change_route(plant_id: str, body: ChangeIn) -> dict:
    plant = _plant_or_404(plant_id)
    if plant.get("ingest_status") != "done":
        raise HTTPException(status_code=409, detail="plant ingest is not done")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="change text is empty")
    from app.store.base import new_id

    store = get_store()
    change_id = new_id()
    job_id = store.create_job({"type": "change", "plant_id": plant_id, "change_id": change_id,
                               "step": "queued", "steps": []})
    runner.submit(job_id, lambda: run_change_job(store, plant_id, change_id, text, job_id))
    return {"job_id": job_id, "change_id": change_id}


@api.get("/changes/{change_id}")
def get_change(change_id: str) -> dict:
    res = get_store().get_change(change_id)
    if res is None:
        raise HTTPException(status_code=404, detail="change not found")
    return res


@api.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = get_store().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


app.include_router(api)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
