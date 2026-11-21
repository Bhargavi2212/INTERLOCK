import pytest
from fastapi.testclient import TestClient

from app import config
from app.api.main import app


@pytest.fixture
def client(monkeypatch):
    # No settings at all: the app must still start and answer.
    for name in config.SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    config.get_settings.cache_clear()
    yield TestClient(app)
    config.get_settings.cache_clear()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "dev"


def test_health_reports_app_version(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "abc1234")
    config.get_settings.cache_clear()
    assert client.get("/health").json()["version"] == "abc1234"


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Interlock" in r.text


def test_secrets_never_in_repr():
    s = config.Settings({"GEMINI_API_KEY": "test-not-a-key", "ACCESS_CODE": "test-code"})
    text = repr(s) + str(s)
    assert "test-not-a-key" not in text
    assert "test-code" not in text
    assert "GEMINI_API_KEY=***" in text


def test_missing_setting_names_variable_only():
    s = config.Settings({})
    with pytest.raises(config.MissingSetting, match="GCS_BUCKET is not set"):
        s.require("GCS_BUCKET")


def test_page_links_static_files_with_version(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "abc1234")
    config.get_settings.cache_clear()
    r = client.get("/")
    assert "/static/app.js?v=abc1234" in r.text and "/static/app.css?v=abc1234" in r.text
    assert r.headers["cache-control"] == "no-cache"
