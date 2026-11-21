import pytest

from app.rules import run_rule
from tests.rules.conftest import bhel_bands, v

# RULES.md R1 test cases (count guarded by test_rules_match_doc.py).
# (flow m3/h, line size, internal diameter mm or None, expected v, status)
RULES_CASES = [
    (105, 100, None, 3.71, "flagged"),
    (210, 100, None, 7.43, "flagged"),
    (210, 150, None, 3.30, "flagged"),
    (210, 200, None, 1.86, "OK"),
    (105, 150, None, 1.65, "OK"),
    (105, 100, 102.3, 3.55, "flagged"),
    (105, None, None, None, "held"),
]


@pytest.mark.parametrize("flow,nb,id_mm,expected_v,status", RULES_CASES)
def test_rules_md_cases(flow, nb, id_mm, expected_v, status):
    inputs = {"flow_total": v(flow, "m3/h")}
    if nb is not None:
        inputs["line_nb"] = v(nb, "NB")
    if id_mm is not None:
        inputs["line_id"] = v(id_mm, "mm")
    r = run_rule("R1", inputs, bhel_bands())
    assert r.status == status
    if expected_v is not None:
        assert round(r.value, 2) == expected_v
    else:
        assert "line_nb" in r.message


def test_below_lower_value_is_information_with_both_facts():
    r = run_rule("R1", {"flow_total": v(210, "m3/h"), "line_nb": v(200, "NB")}, bhel_bands())
    assert r.status == "OK"
    assert r.limit == 2.5
    assert "Part5.pdf p.200" in r.limit_source
    assert any("2.10" in n and "service type not stated" in n for n in r.notes)
    assert any("pump discharge" in a for a in r.assumptions)


def test_below_lower_value_not_solids_is_information_only():
    r = run_rule("R1", {"flow_total": v(210, "m3/h"), "line_nb": v(200, "NB"),
                        "service": v("floor wash water")}, bhel_bands())
    assert r.status == "OK"
    assert any("information only" in n for n in r.notes)


def test_below_lower_value_solids_is_flagged():
    r = run_rule("R1", {"flow_total": v(210, "m3/h"), "line_nb": v(200, "NB"),
                        "service": v("MRS waste water")}, bhel_bands())
    assert r.status == "flagged"
    assert "solids" in r.message


def test_ash_traces_in_floor_wash_are_not_solids():
    # Confirmed 21 Nov: "ash slurry" is solids; ash traces in floor wash are not.
    r = run_rule("R1", {"flow_total": v(210, "m3/h"), "line_nb": v(200, "NB"),
                        "service": v("Floor wash from ESP UNIT 1 containing ash traces")}, bhel_bands())
    assert r.status == "OK"
    assert round(r.value, 2) == 1.86
    assert any("information only" in n for n in r.notes)


def test_ash_slurry_is_solids():
    r = run_rule("R1", {"flow_total": v(210, "m3/h"), "line_nb": v(200, "NB"),
                        "service": v("bottom ash slurry")}, bhel_bands())
    assert r.status == "flagged"


def test_low_side_never_held_even_if_service_disputed():
    from app.rules.model import Disputed
    svc = Disputed((v("water", page=1), v("sludge", page=2)))
    r = run_rule("R1", {"flow_total": v(210, "m3/h"), "line_nb": v(200, "NB"), "service": svc},
                 bhel_bands())
    assert r.status == "OK"


def test_parallel_pumps_upper_bound():
    r = run_rule("R1", {"flow_per_pump": v(105, "m3/h"), "pumps_into_line": v(2, "count"),
                        "line_nb": v(100, "NB")}, bhel_bands())
    assert round(r.value, 2) == 7.43
    assert any("upper bound" in a for a in r.assumptions)


def test_pumps_into_line_missing_is_held():
    r = run_rule("R1", {"flow_per_pump": v(105, "m3/h"), "line_nb": v(100, "NB")}, bhel_bands())
    assert r.status == "held"
    assert "pumps_into_line" in r.message
    assert "do not state in text whether the pumps share one discharge line" in r.message


def test_role_stated_other_uses_default():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(150, "NB"),
                        "line_role": v("drain line")}, bhel_bands())
    assert r.limit == 3.0
    assert r.limit_source.startswith("default")
    assert r.status == "OK"


def _band(low, high, nb_from, nb_to, applies_to, unit="m/s", page=200):
    from app.rules.model import DocLimit
    return DocLimit(rule_id="R1", name="velocity_band", low=low, high=high, unit=unit,
                    applies_from_nb=nb_from, applies_to_nb=nb_to, file="Part5.pdf", page=page,
                    quote=f"{applies_to} {low}-{high}", applies_to=applies_to)


MIXED = [  # mixed order: suction, header, discharge
    _band(0.6, 1.5, 50, None, "pump suction", page=201),
    _band(1.5, 2.0, 50, None, "pump discharge header", page=202),
    _band(1.8, 2.4, 50, 150, "pump discharge", page=200),
]


@pytest.mark.parametrize("role,expected_limit,page", [
    ("pump suction", 1.5, 201),
    ("discharge header", 2.0, 202),
    ("Pump Discharge header to sump", 2.0, 202),
    ("pump discharge", 2.4, 200),
    (None, 2.4, 200),
])
def test_band_by_line_role_mixed_order(role, expected_limit, page):
    ins = {"flow_total": v(105, "m3/h"), "line_nb": v(150, "NB")}
    if role:
        ins["line_role"] = v(role)
    r = run_rule("R1", ins, MIXED)
    assert r.limit == expected_limit and f"p.{page}" in r.limit_source


def test_suction_without_band_uses_suction_default():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(150, "NB"),
                        "line_role": v("pump suction")}, bhel_bands())
    assert r.limit == 1.5 and r.limit_source.startswith("default")


def test_band_with_non_velocity_unit_ignored():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(100, "NB")},
                 [_band(1.8, 2.4, 50, 150, "pump discharge", unit="ft/s")])
    assert r.limit == 3.0


def test_role_pump_discharge_uses_band_without_assumption():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(100, "NB"),
                        "line_role": v("Pump Discharge")}, bhel_bands())
    assert r.limit == 2.4
    assert not any("assumed to be" in a for a in r.assumptions)


def test_no_band_covers_size_uses_default():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(175, "NB")}, bhel_bands())
    assert r.limit == 3.0


def test_doclimit_failed_evidence_is_ignored():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(100, "NB")},
                 bhel_bands(evidence_ok=False))
    assert r.limit == 3.0


def test_no_doc_limits_uses_default_with_confirm_state():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(100, "NB")})
    assert r.limit == 3.0
    assert "default (RULES.md" in r.limit_source


def test_schedule_from_table():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(100, "NB"),
                        "schedule": v("Sch 40")}, bhel_bands())
    assert round(r.value, 2) == 3.55


def test_nps_inches():
    r = run_rule("R1", {"flow_total": v(210, "m3/h"), "line_nb": v(8, "inch")}, bhel_bands())
    assert round(r.value, 2) == 1.86


def test_equal_to_limit_passes():
    # Q chosen so v == 2.4 exactly at 100 NB
    import math
    q = 2.4 * (math.pi / 4 * 0.1 ** 2) * 3600
    r = run_rule("R1", {"flow_total": v(q, "m3/h"), "line_nb": v(100, "NB")}, bhel_bands())
    assert r.status == "OK"
