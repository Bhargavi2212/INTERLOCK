"""models.py routes calls to the right client (no network)."""

import json

from app.reading.models import Models


class FakeInteraction:
    def __init__(self, text):
        self.output_text = text


class FakeInteractions:
    def __init__(self, name, log):
        self.name, self.log = name, log

    def create(self, **kw):
        self.log.append((self.name, sorted(kw)))
        return FakeInteraction(json.dumps({"ok": True}) if "response_format" in kw else "OK")


class FakeClient:
    def __init__(self, name, log):
        self.interactions = FakeInteractions(name, log)


def models_with_fakes(monkeypatch):
    monkeypatch.setenv("MODEL_NEON", "neon-test")
    from app import config
    config.get_settings.cache_clear()
    log = []
    m = Models()
    m._stable, m._beta = FakeClient("stable", log), FakeClient("beta", log)
    return m, log


def test_structured_call_uses_v1beta(monkeypatch):
    m, log = models_with_fakes(monkeypatch)
    assert m.call("understand", "p", schema={"type": "object"}) == {"ok": True}
    assert log[0][0] == "beta" and "response_mime_type" in log[0][1]


def test_plain_call_uses_stable(monkeypatch):
    m, log = models_with_fakes(monkeypatch)
    assert m.call("understand", "p") == "OK"
    assert log[0][0] == "stable" and "response_mime_type" not in log[0][1]
