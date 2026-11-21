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
