"""Change check through the API with a fake models.py and inline jobs (no network)."""

import logging

import pytest

from app.jobs import runner
from app.reading import longread
from app.reading.models import set_models
from tests.test_pipeline_fakes import CHANGE, PAGES, FakeModels

DUMMY_KEY = "dummy-key-AIzaTEST-not-real-0123456789"


@pytest.fixture
def ingested(api, store, monkeypatch):
    monkeypatch.setattr(runner, "INLINE", True)
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    longread._token_cache.clear()
    set_models(FakeModels())
    pid = api.post("/plants", json={"name": "BHEL"}).json()["plant_id"]
    store.put_pages_all(pid, PAGES)
    store.mutate_plant(pid, lambda d: d.update(page_count=len(PAGES), ingest_status="done"))
    yield pid
    set_models(None)


def test_change_route_runs_and_stores(api, store, ingested):
    r = api.post(f"/plants/{ingested}/changes", json={"text": CHANGE}).json()
    job = api.get(f"/jobs/{r['job_id']}").json()
    assert job["state"] == "done" and job["result"]["verdict"] == "BLOCK"
    assert [s["name"] for s in job["steps"]][:2] == ["understand", "long_read"]
    res = api.get(f"/changes/{r['change_id']}").json()
    assert res["verdict"]["verdict"] == "BLOCK"
    assert res["verdict"]["label"] == "BLOCK" and res["page_count"] == len(PAGES)
    names = [s["name"] for s in res["steps"]]
    assert "explain" in names and "headlines" in names            # run in parallel, before verdict
    assert res["explanations"] == [{"note": "explanation unavailable"}]  # fake has no Carbon: verdict unchanged
    assert res["headlines"]                                        # fallback: rule messages


def test_no_conflicts_label_uses_page_count(api, store, ingested):
    from app.verdict import verdict
    assert verdict([], [], [], len(PAGES))["label"] == f"No conflicts found in {len(PAGES)} pages checked"


def test_change_refused_before_ingest(api, store, monkeypatch):
    pid = api.post("/plants", json={"name": "x"}).json()["plant_id"]
    r = api.post(f"/plants/{pid}/changes", json={"text": "anything"})
    assert r.status_code == 409


def test_unknown_change_404(api, store):
    assert api.get("/changes/nope").status_code == 404


def test_no_key_in_logs(api, store, ingested, caplog):
    caplog.set_level(logging.DEBUG)
    api.post(f"/plants/{ingested}/changes", json={"text": CHANGE})
    assert caplog.records  # something was logged
    assert all(DUMMY_KEY not in r.getMessage() for r in caplog.records)
