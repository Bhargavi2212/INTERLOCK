import pytest
from fastapi.testclient import TestClient

from app import config
from app.store.base import set_store
from app.store.memory import MemoryStore

TEST_CODE = "test-access-code"


@pytest.fixture
def store(monkeypatch):
    """A fresh in-memory store and a known access code for API tests."""
    monkeypatch.setenv("ACCESS_CODE", TEST_CODE)
    monkeypatch.setenv("STORE", "memory")
    config.get_settings.cache_clear()
    s = MemoryStore()
    set_store(s)
    yield s
    set_store(None)
    config.get_settings.cache_clear()


@pytest.fixture
def api(store):
    from app.api.main import app

    client = TestClient(app)
    client.headers.update({"X-Access-Code": TEST_CODE})
    return client
