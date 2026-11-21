"""Scenario with fake checked values (no model). The 200 NB demo (PHASE_2 Amendments A3)."""

from app.reading.scenario import build_scenario, doc_limits
from app.rules import run_rules
from app.verdict import BLOCK, verdict

CHANGE = "SG Unit-1 floor wash water transfer pumps: go from 1 working + 1 standby to 2 working + 1 standby."
CHANGES = [{"input": "working", "from": "1", "to": "2", "unit": "count"},
           {"input": "arrangement", "from": "1W+1S", "to": "2W+1S", "unit": ""}]


def d(input, value, unit, file, page, quote=None):
    return {"input": input, "value": value, "unit": unit, "file": file, "page": page,
            "quote": quote or f"{value} {unit}", "evidence_ok": True}


VALUES = [
    d("arrangement", "1W+1S", "", "Part1.pdf", 43),
    d("installed", "2", "nos", "Part1.pdf", 43),
    d("working", "2", "nos", "Part4.pdf", 57),
    d("installed", "2", "nos", "Part4.pdf", 57),
    d("flow_per_pump", "105", "m3/hr", "Part4.pdf", 57),
    d("volume", "105", "m3", "Part4.pdf", 57),
    d("line_nb", "200", "NB", "Part3.pdf", 146),
]
LIMITS = doc_limits([
    {"rule_id": "R1", "low": 1.8, "high": 2.4, "unit": "m/s", "applies_from_nb": 50, "applies_to_nb": 150,
     "applies_to": "pump discharge", "file": "Part5.pdf", "page": 200, "quote": "50-150 mm", "evidence_ok": True},
    {"rule_id": "R1", "low": 2.1, "high": 2.5, "unit": "m/s", "applies_from_nb": 200, "applies_to_nb": None,
     "applies_to": "pump discharge", "file": "Part5.pdf", "page": 200, "quote": "200 mm", "evidence_ok": True},
])
SHARED = [{"value": True, "file": "Part3.pdf", "page": 146, "quote": "(fake: drawing evidence arrives in phase 3)",
           "evidence_ok": True}]


def statuses(results):
    return {r.rule_id: r.status for r in results}


def test_demo_200nb_with_shared_discharge():
    sc = build_scenario(VALUES, SHARED, CHANGES, CHANGE)
    after = run_rules(sc["after"], LIMITS)
    st = statuses(after)
    assert st == {"R1": "OK", "R2": "flagged", "R3": "held"}
    r1 = next(r for r in after if r.rule_id == "R1")
    assert round(r1.value, 2) == 1.86 and r1.notes
    r2 = next(r for r in after if r.rule_id == "R2")
    assert "installed 2 < working 2 + standby 1" in r2.message
    assert any(x["attribute"] == "working" for x in sc["disagreements"])
    v = verdict(after, sc["disagreements"], [], 851)
    assert v["verdict"] == BLOCK


def test_demo_without_shared_discharge_r1_held():
    sc = build_scenario(VALUES, [], CHANGES, CHANGE)
    after = run_rules(sc["after"], LIMITS)
    r1 = next(r for r in after if r.rule_id == "R1")
    assert r1.status == "held"
    assert "do not state in text whether the pumps share one discharge line" in r1.message
    assert verdict(after, sc["disagreements"], [], 851)["verdict"] == BLOCK


def test_same_value_on_several_pages_merges():
    sc = build_scenario(VALUES, SHARED, CHANGES, CHANGE)
    assert len(sc["sources"]["installed"]) == 2
    assert sc["issued"]["R2"]["installed"].page == 43  # first cited


def test_different_values_disputed_and_disagreement_when_touched():
    vals = VALUES + [d("flow_per_pump", "120", "m3/hr", "Part3.pdf", 146)]
    sc = build_scenario(vals, SHARED, CHANGES + [{"input": "flow_per_pump", "to": "105", "unit": "m3/h"}], CHANGE)
    from app.rules.model import Disputed
    assert isinstance(sc["issued"]["R1"]["flow_per_pump"], Disputed)
    assert any(x["attribute"] == "flow_per_pump" for x in sc["disagreements"])


def test_untouched_different_values_disputed_without_disagreement():
    vals = VALUES + [d("volume", "100", "m3", "Part3.pdf", 146)]
    sc = build_scenario(vals, SHARED, CHANGES, CHANGE)
    assert not any(x["attribute"] == "volume" for x in sc["disagreements"])


def test_failed_evidence_values_never_used():
    vals = [dict(v) for v in VALUES]
    vals[-1]["evidence_ok"] = False  # line_nb
    sc = build_scenario(vals, SHARED, CHANGES, CHANGE)
    assert "line_nb" not in sc["after"]["R1"]


def test_q_out_is_flow_times_working():
    sc = build_scenario(VALUES, SHARED, CHANGES, CHANGE)
    assert sc["after"]["R3"]["q_out"].value == 210
    assert sc["issued"]["R3"]["q_out"].value == 210  # data sheet 2W


def test_shared_false_means_one_pump():
    shared_false = [{**SHARED[0], "value": False}]
    sc = build_scenario(VALUES, shared_false, CHANGES, CHANGE)
    assert sc["after"]["R1"]["pumps_into_line"].value == 1


def test_register_overlay_replaces_issued_value():
    reg = [{"entry_id": "reg-1", "item": "SG Unit-1 floor wash water transfer pumps",
            "attribute": "installed", "value": 3, "unit": "count"}]
    sc = build_scenario(VALUES, SHARED, CHANGES, CHANGE, reg)
    assert sc["issued"]["R2"]["installed"].value == 3
    assert sc["issued"]["R2"]["installed"].source == "register"
    after = run_rules(sc["after"], LIMITS)
    assert statuses(after)["R2"] == "OK"


def test_always_r1_to_r3_for_pumps():
    sc = build_scenario([], [], [], "")
    assert set(sc["after"]) == {"R1", "R2", "R3"}
    assert all(r.status == "held" for r in run_rules(sc["after"], []))
