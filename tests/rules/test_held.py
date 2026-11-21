import pytest

from app.rules import run_rule, run_rules
from app.rules.model import Disputed
from tests.rules.conftest import bhel_bands, v

BASE = {"flow_total": v(105, "m3/h"), "line_nb": v(100, "NB")}


def test_missing_input_is_held_and_named():
    r = run_rule("R1", {"line_nb": v(100, "NB")})
    assert r.status == "held"
    assert "flow" in r.message


def test_failed_evidence_is_held():
    r = run_rule("R1", {**BASE, "flow_total": v(105, "m3/h", evidence_ok=False)})
    assert r.status == "held"
    assert "flow_total" in r.message and "evidence check failed" in r.message


def test_disputed_is_held_listing_pages():
    d = Disputed((v(1, "count", page=4), v(2, "count", page=57)))
    r = run_rule("R2", {"installed": v(2, "count"), "working": d})
    assert r.status == "held"
    assert "working" in r.message and "p.4" in r.message and "p.57" in r.message


def test_unknown_unit_is_held_with_unit_named():
    r = run_rule("R1", {**BASE, "flow_total": v(105, "gpm")})
    assert r.status == "held"
    assert "flow_total" in r.message and "gpm" in r.message


def test_number_with_empty_unit_is_held():
    r = run_rule("R1", {**BASE, "flow_total": v(105, "")})
    assert r.status == "held"
    assert "no unit" in r.message


def test_change_source_value_without_file_is_accepted():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(200, "NB", source="fix")},
                 bhel_bands())
    assert r.status == "OK"
    assert "fix text" in r.message


def test_change_value_skips_evidence_flag():
    # evidence_ok applies to document values only
    from app.rules.model import Value
    fix = Value(200, "NB", quote="200 NB header", evidence_ok=False, source="fix")
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": fix}, bhel_bands())
    assert r.status == "OK"


def test_run_rules_live_only():
    out = run_rules({"R1": BASE, "R4": {}}, bhel_bands())
    assert [r.rule_id for r in out] == ["R1"]


def test_no_guessing_every_result_has_formula_and_inputs():
    r = run_rule("R1", BASE, bhel_bands())
    assert r.formula and r.inputs == BASE


@pytest.mark.parametrize("rule,inputs,name", [
    ("R1", {"flow_total": v(0, "m3/h"), "line_nb": v(100, "NB")}, "flow_total"),
    ("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(0, "NB")}, "line_nb"),
    ("R1", {"flow_total": v(105, "m3/h"), "line_id": v(-5, "mm")}, "line_id"),
    ("R3", {"volume": v(0, "m3"), "q_out": v(60, "m3/h"), "q_in": v(30, "m3/h")}, "volume"),
    ("R6", {"dose": v(2, "mg/L"), "flow": v(500, "m3/h"), "strength": v(0, "% w/v"),
            "pump_min": v(1, "L/h"), "pump_max": v(5, "L/h")}, "strength"),
    ("R6", {"dose": v(2, "mg/L"), "flow": v(500, "m3/h"), "strength": v(10, "% w/w"), "density": v(0, "kg/L"),
            "pump_min": v(1, "L/h"), "pump_max": v(5, "L/h")}, "density"),
])
def test_non_positive_physical_quantity_is_held(rule, inputs, name):
    r = run_rule(rule, inputs)  # never ZeroDivisionError
    assert r.status == "held" and name in r.message and "must be > 0" in r.message


def test_zero_gauge_pressure_and_zero_standby_allowed():
    r = run_rule("R5", {"max_suction": v(0, "bar(g)"), "shutoff_head": v(9.0, "bar(g)"), "design": v(10, "bar(g)")})
    assert r.status == "OK"
    r = run_rule("R2", {"installed": v(2, "count"), "working": v(2, "count"), "standby_required": v(0, "count")})
    assert r.status == "OK"


def test_percent_arrangement_gives_installed_when_missing():
    r = run_rule("R2", {"arrangement": v("3X100%")})
    assert r.status == "OK"  # installed 3 >= working 1 + standby 2
    assert any("installed count taken from the arrangement" in a for a in r.assumptions)


def test_arrangement_not_parsed_when_not_needed():
    r = run_rule("R2", {"installed": v(2, "count"), "working": v(1, "count"),
                        "standby_required": v(1, "count"), "arrangement": v("not an arrangement")})
    assert r.status == "OK"
