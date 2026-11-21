"""Firestore + Cloud Storage store (ARCHITECTURE.md section 5).

Credentials: Application Default Credentials (the Cloud Run service account in
production; Bhargavi's `gcloud auth application-default login` locally).
Signed upload URLs are signed through the IAM signBlob API with the runtime
service account (no key file; needs roles/iam.serviceAccountTokenCreator).
"""

from __future__ import annotations

import copy
import json
import threading
from datetime import timedelta

from app.config import get_settings
from app.store.base import file_object, new_id, now, strip_page_text

SIGNED_URL_MINUTES = 30
FIELD_LIMIT_BYTES = 900_000  # Firestore documents are capped at 1 MiB


class GcpStore:
    def __init__(self):
        from google.cloud import firestore, storage

        s = get_settings()
        project = s.require("GCP_PROJECT")
        self.db = firestore.Client(project=project, database=s.get("FIRESTORE_DATABASE"))
        self.gcs = storage.Client(project=project)
        self.bucket = self.gcs.bucket(s.require("GCS_BUCKET"))
        self._lock = threading.Lock()
        self._pages_all_cache: dict[str, list[dict]] = {}

    # ------------------------------------------------------------ plants
    def _plant_ref(self, plant_id):
        return self.db.collection("plants").document(plant_id)

    def create_plant(self, name):
        pid = new_id()
        doc = {"plant_id": pid, "name": name, "created_at": now(), "files": [],
               "page_count": 0, "ingest_status": "empty", "token_count": None}
        self._plant_ref(pid).set(doc)
        return doc

    def get_plant(self, plant_id):
        snap = self._plant_ref(plant_id).get()
        return snap.to_dict() if snap.exists else None

    def list_plants(self):
        return [d.to_dict() for d in self.db.collection("plants").stream()]

    def mutate_plant(self, plant_id, fn):
        # One Cloud Run instance today (ARCHITECTURE section 7): a process lock is enough.
        with self._lock:
            doc = self.get_plant(plant_id)
            if doc is None:
                raise KeyError(plant_id)
            fn(doc)
            self._plant_ref(plant_id).set(doc)
            return doc

    # ------------------------------------------------------------ uploaded files
    def signed_put_url(self, plant_id, relative_path):
        import google.auth
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        email = getattr(creds, "service_account_email", None)
        if not email or email == "default":
            raise RuntimeError("signed URLs need a service account (run on Cloud Run)")
        blob = self.bucket.blob(file_object(plant_id, relative_path))
        return blob.generate_signed_url(
            version="v4", method="PUT", content_type="application/pdf",
            expiration=timedelta(minutes=SIGNED_URL_MINUTES),
            service_account_email=email, access_token=creds.token,
        )

    def file_exists(self, plant_id, relative_path):
        return self.bucket.blob(file_object(plant_id, relative_path)).exists()

    def download_file(self, plant_id, relative_path, dest):
        self.bucket.blob(file_object(plant_id, relative_path)).download_to_filename(dest)

    # ------------------------------------------------------------ pages
    def put_page(self, plant_id, n, data):
        self.bucket.blob(f"plants/{plant_id}/pages/{n}.json").upload_from_string(
            json.dumps(data, ensure_ascii=False), content_type="application/json")

    def get_page(self, plant_id, n):
        blob = self.bucket.blob(f"plants/{plant_id}/pages/{n}.json")
        return json.loads(blob.download_as_text()) if blob.exists() else None

    def put_page_png(self, plant_id, n, png):
        self.bucket.blob(f"plants/{plant_id}/pages/{n}.png").upload_from_string(png, content_type="image/png")

    def get_page_png(self, plant_id, n):
        blob = self.bucket.blob(f"plants/{plant_id}/pages/{n}.png")
        return blob.download_as_bytes() if blob.exists() else None

    def put_change_png(self, plant_id, change_id, png):
        self.bucket.blob(f"plants/{plant_id}/changes/{change_id}/drawing.png").upload_from_string(
            png, content_type="image/png")

    def get_change_png(self, change_id):
        idx = self.db.collection("change_index").document(change_id).get()
        if not idx.exists:
            return None
        blob = self.bucket.blob(f"plants/{idx.to_dict()['plant_id']}/changes/{change_id}/drawing.png")
        return blob.download_as_bytes() if blob.exists() else None

    def put_pages_all(self, plant_id, pages):
        self.bucket.blob(f"plants/{plant_id}/pages_all.json").upload_from_string(
            json.dumps(pages, ensure_ascii=False), content_type="application/json")
        self._pages_all_cache.pop(plant_id, None)

    def forget_pages_cache(self, plant_id):
        self._pages_all_cache.pop(plant_id, None)

    def get_pages_all(self, plant_id):
        """Every page {n, file, page, text} in n order; cached in memory per plant.
        Returns a copy, so a caller cannot change the cache."""
        if plant_id not in self._pages_all_cache:
            blob = self.bucket.blob(f"plants/{plant_id}/pages_all.json")
            self._pages_all_cache[plant_id] = json.loads(blob.download_as_text()) if blob.exists() else []
        return copy.deepcopy(self._pages_all_cache[plant_id])

    # ------------------------------------------------------------ changes
    def put_change(self, plant_id, change_id, data):
        """Whole record > 900 KB -> the full result goes to GCS, Firestore keeps a pointer.
        Page text is never stored in a change record."""
        doc = strip_page_text(data)
        raw = json.dumps(doc, ensure_ascii=False)
        if len(raw.encode()) > FIELD_LIMIT_BYTES:
            path = f"plants/{plant_id}/changes/{change_id}/result.json"
            self.bucket.blob(path).upload_from_string(raw, content_type="application/json")
            doc = {"change_id": change_id, "plant_id": plant_id, "result_gcs": path,
                   "verdict": doc.get("verdict")}
        self._plant_ref(plant_id).collection("changes").document(change_id).set(doc)
        self.db.collection("change_index").document(change_id).set({"plant_id": plant_id})

    def get_change(self, change_id):
        idx = self.db.collection("change_index").document(change_id).get()
        if not idx.exists:
            return None
        plant_id = idx.to_dict()["plant_id"]
        snap = self._plant_ref(plant_id).collection("changes").document(change_id).get()
        if not snap.exists:
            return None
        doc = snap.to_dict()
        if "result_gcs" in doc:
            return json.loads(self.bucket.blob(doc["result_gcs"]).download_as_text())
        return doc

    # ------------------------------------------------------------ jobs
    def create_job(self, data):
        jid = new_id()
        self.db.collection("jobs").document(jid).set(
            {"job_id": jid, "state": "queued", "created_at": now(), "updated_at": now(), **data})
        return jid

    def update_job(self, job_id, fields):
        self.db.collection("jobs").document(job_id).set({**fields, "updated_at": now()}, merge=True)

    def get_job(self, job_id):
        snap = self.db.collection("jobs").document(job_id).get()
        return snap.to_dict() if snap.exists else None

    def unfinished_jobs(self):
        out = []
        for state in ("queued", "running"):
            out += [d.to_dict() for d in self.db.collection("jobs").where("state", "==", state).stream()]
        return out

    # ------------------------------------------------------------ register
    def list_register(self, plant_id):
        return [d.to_dict() | {"entry_id": d.id}
                for d in self._plant_ref(plant_id).collection("register").stream()]
