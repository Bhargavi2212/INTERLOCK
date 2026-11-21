"""Approve -> register; clash end to end (no network; fakes)."""

import json

import pytest

from app.reading import pipeline
from tests.test_agent_recheck import stored  # noqa: F401  (fixture)
from tests.test_drawing_pipeline import SeeModels, plant  # noqa: F401  (fixture)

FIX = [{"input": "installed", "from": "2", "to": "3", "unit": "count", "why": "add a third pump"}]


def with_fix(s, change, fix=FIX, proven=True):
    change["fix"] = {"outcome": "proposed", "fix": fix, "recheck": {"proven": proven}}
    s.put_change(change["plant_id"], change["change_id"], change)
    return json.loads(json.dumps(s.get_change(change["change_id"])))


@pytest.fixture
def api_with(api, store, stored):  # noqa: F811
    s, change = stored
    # serve the stored change through the API's store
    store.plants.update(s.plants)
    store.pages_all.update(s.pages_all)
    store.pages.update(s.pages)
    return api, store, change


def test_approve_409_without_proven_fix(api_with):
    api, store, change = api_with
    store.put_change(change["plant_id"], change["change_id"], change)
    r = api.post(f"/changes/{change['change_id']}/approve", json={"resolved": []})
    assert r.status_code == 409 and "no proven fix" in r.json()["detail"]


def test_approve_409_until_disagreements_ticked(api_with):
    api, store, change = api_with
    change = with_fix(store, change)
    assert [d["attribute"] for d in change["disagreements"]] == ["working"]
    r = api.post(f"/changes/{change['change_id']}/approve", json={"resolved": []})
    assert r.status_code == 409 and "documents disagree" in r.json()["detail"] and "working" in r.json()["detail"]


def test_approve_writes_entries_with_unit_tag_and_tick(api_with):
    api, store, change = api_with
    change = with_fix(store, change)
    resolved = [d["attribute"] for d in change["disagreements"]]
    r = api.post(f"/changes/{change['change_id']}/approve", json={"resolved": resolved})
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]
    attrs = {(e["attribute"], str(e["value"]), e["fix"]) for e in entries}
    assert ("installed", "3", True) in attrs and ("working", "2", False) in attrs
    assert all(e["unit_tag"] == "Unit-1" and e["resolved_disagreements"] for e in entries)
    listed = api.get(f"/plants/{change['plant_id']}/register").json()
    assert {e["entry_id"] for e in listed} == {e["entry_id"] for e in entries}


def test_approve_reruns_recheck(api_with):
    api, store, change = api_with
    change = with_fix(store, change, fix=[{"input": "installed", "to": "9", "unit": "count", "why": "x"}])
    resolved = [d["attribute"] for d in change["disagreements"]]
    r = api.post(f"/changes/{change['change_id']}/approve", json={"resolved": resolved})
    assert r.status_code == 409 and "no longer proven" in r.json()["detail"]


class RemoveThirdPump(SeeModels):
    def call(self, role, prompt, schema=None, thinking="low", usage=None):
        out = super().call(role, prompt, schema, thinking, usage)
        if role == "understand":
            out["changes"] = [{"input": "installed", "from": "3", "to": "2", "unit": "count"}]
        return out


def test_clash_end_to_end_after_approval(api_with):
    api, store, change = api_with
    change = with_fix(store, change)
    api.post(f"/changes/{change['change_id']}/approve",
             json={"resolved": [d["attribute"] for d in change["disagreements"]]})
    later = pipeline.check_change(store, RemoveThirdPump(), change["plant_id"], "c2",
                                  "SG Unit-1 floor wash pumps: remove the third pump")
    assert later["verdict"]["verdict"] == "BLOCK"
    assert any("clashes with approved change" in r and "installed approved 3, proposed 2" in r
               for r in later["verdict"]["reasons"])
