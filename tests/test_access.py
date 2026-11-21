from fastapi.testclient import TestClient

from app import config
from app.api.main import app
from tests.conftest import TEST_CODE


def test_protected_route_needs_code(store):
    pid = store.create_plant("p")["plant_id"]
    c = TestClient(app)
    assert c.get(f"/plants/{pid}").status_code == 401
    assert c.get(f"/plants/{pid}").json() == {"detail": "access code required"}
    assert c.get(f"/plants/{pid}", headers={"X-Access-Code": "wrong"}).status_code == 401
    assert c.get(f"/plants/{pid}", headers={"X-Access-Code": TEST_CODE}).status_code == 200


def test_unset_code_is_503_never_open(store, monkeypatch):
    monkeypatch.delenv("ACCESS_CODE", raising=False)
    config.get_settings.cache_clear()
    c = TestClient(app)
    r = c.get("/plants/x", headers={"X-Access-Code": "anything"})
    assert r.status_code == 503
    assert r.json()["detail"] == "access code not configured"


def test_health_and_page_stay_open(store):
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/").status_code == 200


def test_jobs_protected(store):
    assert TestClient(app).get("/jobs/x").status_code == 401


def test_code_never_echoed(store):
    r = TestClient(app).get("/plants/x", headers={"X-Access-Code": "guess-123"})
    assert "guess-123" not in r.text and TEST_CODE not in r.text
