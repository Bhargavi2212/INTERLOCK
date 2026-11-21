"""Store interface (ARCHITECTURE.md section 5). Backends: gcp (default), memory (tests).

Layout:
  GCS       plants/{plant_id}/files/{relative_path}         uploaded PDFs
            plants/{plant_id}/pages/{n}.json, {n}.png       page text+words; PNG for drawings
            plants/{plant_id}/pages_all.json                every page {n, file, page, text} in n order
            plants/{plant_id}/changes/{change_id}/...       large result fields
  Firestore plants/{plant_id}, plants/{plant_id}/changes/{change_id},
            plants/{plant_id}/register/{entry_id}, change_index/{change_id}, jobs/{job_id}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, Protocol


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_object(plant_id: str, relative_path: str) -> str:
    return f"plants/{plant_id}/files/{relative_path}"


class Store(Protocol):
    # plants
    def create_plant(self, name: str) -> dict: ...
    def get_plant(self, plant_id: str) -> dict | None: ...
    def mutate_plant(self, plant_id: str, fn: Callable[[dict], None]) -> dict: ...

    # uploaded files
    def signed_put_url(self, plant_id: str, relative_path: str) -> str: ...
    def file_exists(self, plant_id: str, relative_path: str) -> bool: ...
    def download_file(self, plant_id: str, relative_path: str, dest: str) -> None: ...

    # pages
    def put_page(self, plant_id: str, n: int, data: dict) -> None: ...
    def get_page(self, plant_id: str, n: int) -> dict | None: ...
    def put_page_png(self, plant_id: str, n: int, png: bytes) -> None: ...
    def put_pages_all(self, plant_id: str, pages: list[dict]) -> None: ...
    def get_pages_all(self, plant_id: str) -> list[dict]: ...

    # changes
    def put_change(self, plant_id: str, change_id: str, data: dict) -> None: ...
    def get_change(self, change_id: str) -> dict | None: ...

    # jobs
    def create_job(self, data: dict) -> str: ...
    def update_job(self, job_id: str, fields: dict) -> None: ...
    def get_job(self, job_id: str) -> dict | None: ...
    def unfinished_jobs(self) -> list[dict]: ...

    # register (read in phase 2; written in phase 4)
    def list_register(self, plant_id: str) -> list[dict]: ...


_store: Store | None = None


def get_store() -> Store:
    """The backend named by STORE (default gcp); one instance per process."""
    global _store
    if _store is None:
        from app.config import get_settings

        kind = get_settings().get("STORE")
        if kind == "memory":
            from app.store.memory import MemoryStore
            _store = MemoryStore()
        elif kind == "gcp":
            from app.store.gcp import GcpStore
            _store = GcpStore()
        else:
            raise ValueError(f"STORE must be gcp or memory, not '{kind}'")
    return _store


def set_store(store: Store | None) -> None:
    """Tests install a MemoryStore here."""
    global _store
    _store = store
