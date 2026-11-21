"""Server re-check over a stored change result (no network)."""

import json

import pytest

from app.agent.recheck import rebuild, recheck
from tests.test_drawing_pipeline import SeeModels, plant, run  # noqa: F401  (fixture)


@pytest.fixture
def stored(plant):  # noqa: F811
    s, pid = plant
    res = run(plant, SeeModels())
    s.put_change(pid, "c1", res)
    return s, json.loads(json.dumps(s.get_change("c1")))   # exactly what Firestore gives back


def key(r):
    return (r["rule_id"], r["status"], r["value"], r["limit"], r["limit_source"], tuple(r["assumptions"]),
            tuple(r["notes"]))


def test_rebuild_without_fix_reproduces_results_after(stored):
    s, change = stored
    again = [r.to_dict() for r in rebuild(s, change)["results"]]
    assert [key(r) for r in again] == [key(r) for r in change["results_after"]]


def test_demo1_third_pump_is_proven(stored):
    s, change = stored
    out = recheck(s, change, [{"input": "installed", "from": "2", "to": "3", "unit": "count", "why": "add a pump"}])
    assert out["proven"], out["reasons"]
    st = {r["rule_id"]: r["status"] for r in out["results_fixed"]}
    assert st == {"R1": "OK", "R2": "OK", "R3": "held"}          # R3 was held before: allowed


def test_agent_says_proposed_but_server_finds_r1_flagged(stored):
    s, change = stored
    out = recheck(s, change, [{"input": "installed", "to": "3", "unit": "count", "why": "pump"},
                              {"input": "line_nb", "to": "50", "unit": "NB", "why": "smaller pipe"}])
    assert not out["proven"] and any("R1" in r for r in out["reasons"])


@pytest.mark.parametrize("fix,why", [
    ([{"input": "installed", "to": "9", "unit": "count"}], "not 2 +"),
    ([{"input": "arrangement", "to": "2W+2S", "unit": ""}], "outside the allowed levers: arrangement"),
    ([{"input": "line_nb", "to": "175", "unit": "NB"}], "not a standard size"),
    ([], "changes nothing"),
])
def test_outside_lever_refused(stored, fix, why):
    s, change = stored
    out = recheck(s, change, fix)
    assert not out["proven"] and not out["levers_ok"] and why in out["reasons"][0]


def test_clash_after_approval_not_proven(stored):
    s, change = stored
    s.register[change["plant_id"]] = [{"entry_id": "reg-1", "item": change["understanding"]["item"],
                                       "names": change["understanding"]["names"], "unit_tag": "Unit-1",
                                       "attribute": "installed", "value": 3, "unit": "count",
                                       "approved_at": "2026-11-21T15:00:00+00:00"}]
    out = recheck(s, change, [{"input": "installed", "to": "4", "unit": "count", "why": "another pump"}])
    assert not out["proven"] and out["clashes"] and "reg-1" in " ".join(out["reasons"])
