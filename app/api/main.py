"""FastAPI app. Phase 0: health check and the placeholder page only."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.config import get_settings

WEB_DIR = Path(__file__).resolve().parents[2] / "web"

app = FastAPI(title="Interlock")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": get_settings().app_version}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
