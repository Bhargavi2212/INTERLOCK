"""GcpStore logic with in-process fakes of GCS and Firestore (no network)."""

import json
import threading

from app.store.gcp import FIELD_LIMIT_BYTES, GcpStore


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name

    def exists(self):
        return self.name in self.bucket.data

    def upload_from_string(self, data, content_type=None):
        self.bucket.data[self.name] = data if isinstance(data, str) else data.decode("latin-1")

    def download_as_text(self):
        return self.bucket.data[self.name]


class FakeBucket:
    def __init__(self):
        self.data = {}

    def blob(self, name):
        return FakeBlob(self, name)


class FakeSnap:
    def __init__(self, doc_id, data):
        self.id, self._data = doc_id, data
        self.exists = data is not None

    def to_dict(self):
        return json.loads(json.dumps(self._data))


class FakeDoc:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def set(self, data, merge=False):
        self.db.docs[self.path] = {**self.db.docs.get(self.path, {}), **data} if merge else dict(data)

    def get(self):
        return FakeSnap(self.path.split("/")[-1], self.db.docs.get(self.path))

    def collection(self, name):
        return FakeCollection(self.db, f"{self.path}/{name}")


class FakeCollection:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, doc_id):
        return FakeDoc(self.db, f"{self.path}/{doc_id}")


class FakeDB:
    def __init__(self):
        self.docs = {}

    def collection(self, name):
        return FakeCollection(self, name)


def fake_store():
    s = GcpStore.__new__(GcpStore)
    s.bucket, s.db = FakeBucket(), FakeDB()
    s._lock, s._pages_all_cache = threading.Lock(), {}
    return s


def test_pages_all_returns_a_copy():
    s = fake_store()
    s.put_pages_all("p", [{"n": 0, "file": "a.pdf", "page": 1, "text": "x"}])
    first = s.get_pages_all("p")
    first.append({"n": 99})
    first[0]["text"] = "changed"
    again = s.get_pages_all("p")
    assert again == [{"n": 0, "file": "a.pdf", "page": 1, "text": "x"}]


def test_small_change_stored_in_firestore_without_page_text():
    s = fake_store()
    s.put_change("p", "c1", {"text": "the change", "verdict": {"verdict": "BLOCK"},
                             "pages": [{"file": "a.pdf", "page": 1, "text": "PAGE TEXT", "words": [[0, 0, 1, 1, "x"]]}]})
    stored = s.db.docs["plants/p/changes/c1"]
    assert stored["pages"] == [{"file": "a.pdf", "page": 1}]
    assert "PAGE TEXT" not in json.dumps(stored)
    assert s.get_change("c1")["text"] == "the change"


def test_large_change_goes_to_gcs_with_pointer():
    s = fake_store()
    big = {"text": "c", "verdict": {"verdict": "REVIEW"}, "values": [{"quote": "q" * 1000}] * (FIELD_LIMIT_BYTES // 900)}
    s.put_change("p", "c2", big)
    stored = s.db.docs["plants/p/changes/c2"]
    assert stored["result_gcs"] == "plants/p/changes/c2/result.json"
    assert stored["verdict"] == {"verdict": "REVIEW"} and "values" not in stored
    assert s.get_change("c2")["values"] == big["values"]
