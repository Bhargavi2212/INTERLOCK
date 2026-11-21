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


def test_change_arrangement_never_sets_standby():
    vals = [d("installed", "3", "nos", "Part1.pdf", 43), d("arrangement", "2W+1S", "", "Part1.pdf", 43)]
    sc = build_scenario(vals, [], [{"input": "arrangement", "from": "2W+1S", "to": "3W", "unit": ""}], "run all three")
    assert sc["after"]["R2"]["arrangement"].value == "2W+1S"  # documents' arrangement kept
    assert sc["after"]["R2"]["working"].value == 3
    r2 = next(r for r in run_rules(sc["after"], []) if r.rule_id == "R2")
    assert r2.status == "flagged"


def test_one_working_pump_is_one_pump_into_the_line():
    vals = [d("arrangement", "1W+1S", "", "Part1.pdf", 43), d("working", "1", "nos", "Part4.pdf", 56),
            d("flow_per_pump", "20", "m3/hr", "Part4.pdf", 56), d("line_nb", "50", "NB", "Part3.pdf", 146)]
    sc = build_scenario(vals, [], [], "")  # no shared_discharge value at all
    assert sc["issued"]["R1"]["pumps_into_line"].value in ("1", 1)
    r1 = next(r for r in run_rules(sc["issued"], LIMITS) if r.rule_id == "R1")
    assert r1.status == "flagged" and round(r1.value, 2) == 2.83  # 20 m3/h in 50 NB


def test_service_only_from_fluid_to_be_handled():
    item_name = d("service", "SG UNIT-1 WASTE WATER TRANSFER PUMPS", "", "Part1.pdf", 43,
                  quote="SG UNIT-1 WASTE WATER TRANSFER PUMPS")
    sc = build_scenario(VALUES + [item_name], SHARED, CHANGES, CHANGE)
    assert "service" not in sc["after"]["R1"]  # the item name never reaches R1

    fluid = d("service", "Floor wash from ESP UNIT 1 containing ash traces", "", "Part4.pdf", 57,
              quote="Fluid to be handled Floor wash from ESP UNIT 1 containing ash traces")
    sc = build_scenario(VALUES + [item_name, fluid], SHARED, CHANGES, CHANGE)
    assert sc["after"]["R1"]["service"].value.startswith("Floor wash")
    r1 = next(r for r in run_rules(sc["after"], LIMITS) if r.rule_id == "R1")
    assert r1.status == "OK" and round(r1.value, 2) == 1.86   # 210 m3/h in 200 NB


def test_disputed_standby_uses_stricter_value_and_still_blocks():
    vals = [d("arrangement", "1W+1S", "", "Part1.pdf", 43),          # scope
            d("arrangement", "2W", "", "Part4.pdf", 57),             # data sheet
            d("installed", "2", "nos", "Part4.pdf", 57)]
    changes = [{"input": "working", "from": "1", "to": "2", "unit": "count"}]
    sc = build_scenario(vals, [], changes, CHANGE)
    r2 = next(r for r in run_rules(sc["after"], []) if r.rule_id == "R2")
    assert r2.status == "flagged"                                      # 2 < 2 + 1
    note = " ".join(r2.assumptions)
    assert "Part1.pdf p.43 = 1W+1S" in note and "Part4.pdf p.57 = 2W" in note and "stricter value, standby 1" in note
    v = verdict(run_rules(sc["after"], []), sc["disagreements"], [], 851)
    assert v["verdict"] == BLOCK
    assert any("arrangement" in r and "Part1.pdf p.43" in r for r in v["reasons"])


def test_disputed_installed_count_stays_held():
    vals = [d("arrangement", "1W+1S", "", "Part1.pdf", 43), d("installed", "2", "nos", "Part1.pdf", 43),
            d("installed", "3", "nos", "Part4.pdf", 57)]
    sc = build_scenario(vals, [], [{"input": "working", "to": "2", "unit": "count"}], CHANGE)
    r2 = next(r for r in run_rules(sc["after"], []) if r.rule_id == "R2")
    assert r2.status == "held" and "installed" in r2.message
