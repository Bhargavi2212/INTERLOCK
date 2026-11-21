"""FastAPI app: /health, the one screen, and the protected API (ARCHITECTURE.md section 6)."""

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.access import require_access
from app.config import get_settings
from app.store.base import get_store

WEB_DIR = Path(__file__).resolve().parents[2] / "web"

app = FastAPI(title="Interlock")
api = APIRouter(dependencies=[Depends(require_access)])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": get_settings().app_version}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@api.get("/plants/{plant_id}")
def get_plant(plant_id: str) -> dict:
    plant = get_store().get_plant(plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail="plant not found")
    return plant


@api.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = get_store().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


app.include_router(api)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
