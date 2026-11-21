"""In-memory store for tests. Same interface as GcpStore."""

from __future__ import annotations

import copy
import threading

from app.store.base import file_object, new_id, now, strip_page_text


class MemoryStore:
    def __init__(self):
        self.plants: dict[str, dict] = {}
        self.blobs: dict[str, bytes] = {}
        self.pages: dict[tuple[str, int], dict] = {}
        self.pngs: dict[tuple[str, int], bytes] = {}
        self.pages_all: dict[str, list[dict]] = {}
        self.changes: dict[str, dict] = {}
        self.change_index: dict[str, str] = {}
        self.jobs: dict[str, dict] = {}
        self.register: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    # plants
    def create_plant(self, name):
        pid = new_id()
        self.plants[pid] = {"plant_id": pid, "name": name, "created_at": now(), "files": [],
                            "page_count": 0, "ingest_status": "empty", "token_count": None}
        return copy.deepcopy(self.plants[pid])

    def get_plant(self, plant_id):
        p = self.plants.get(plant_id)
        return copy.deepcopy(p) if p else None

    def mutate_plant(self, plant_id, fn):
        with self._lock:
            p = self.plants[plant_id]
            fn(p)
            return copy.deepcopy(p)

    # uploaded files
    def signed_put_url(self, plant_id, relative_path):
        return f"memory://upload/{file_object(plant_id, relative_path)}"

    def put_blob(self, plant_id, relative_path, data: bytes):
        """Test helper: what a browser PUT would do."""
        self.blobs[file_object(plant_id, relative_path)] = data

    def file_exists(self, plant_id, relative_path):
        return file_object(plant_id, relative_path) in self.blobs

    def download_file(self, plant_id, relative_path, dest):
        with open(dest, "wb") as f:
            f.write(self.blobs[file_object(plant_id, relative_path)])

    # pages
    def put_page(self, plant_id, n, data):
        self.pages[(plant_id, n)] = copy.deepcopy(data)

    def get_page(self, plant_id, n):
        return copy.deepcopy(self.pages.get((plant_id, n)))

    def put_page_png(self, plant_id, n, png):
        self.pngs[(plant_id, n)] = png

    def put_pages_all(self, plant_id, pages):
        self.pages_all[plant_id] = copy.deepcopy(pages)

    def get_pages_all(self, plant_id):
        return copy.deepcopy(self.pages_all.get(plant_id, []))

    # changes
    def put_change(self, plant_id, change_id, data):
        self.changes[change_id] = strip_page_text(data)
        self.change_index[change_id] = plant_id

    def get_change(self, change_id):
        return copy.deepcopy(self.changes.get(change_id))

    # jobs
    def create_job(self, data):
        jid = new_id()
        self.jobs[jid] = {"job_id": jid, "state": "queued", "created_at": now(), "updated_at": now(), **data}
        return jid

    def update_job(self, job_id, fields):
        with self._lock:
            self.jobs[job_id].update(copy.deepcopy(fields))
            self.jobs[job_id]["updated_at"] = now()

    def get_job(self, job_id):
        return copy.deepcopy(self.jobs.get(job_id))

    def unfinished_jobs(self):
        return [copy.deepcopy(j) for j in self.jobs.values() if j.get("state") in ("queued", "running")]

    # register
    def list_register(self, plant_id):
        return copy.deepcopy(self.register.get(plant_id, []))

