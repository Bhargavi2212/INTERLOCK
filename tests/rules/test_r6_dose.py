import pytest

from app.rules import run_rule
from tests.rules.conftest import v

# RULES.md R6 test cases: (dose mg/L, flow m3/h, strength %, kind, density, pump L/h, expected L/h, status)
RULES_CASES = [
    (2, 500, 10, "w/v", None, (21.6, 444), 10.0, "flagged"),
    (20, 500, 10, "w/v", None, (21.6, 444), 100.0, "OK"),
    (2, 500, 10, "w/w", 1.2, (0.5, 5), 8.33, "flagged"),
]


def inputs(dose, flow, strength, kind, density, pump):
    d = {"dose": v(dose, "mg/L"), "flow": v(flow, "m3/h"), "strength": v(strength, f"% {kind}"),
         "pump_min": v(pump[0], "L/h"), "pump_max": v(pump[1], "L/h")}
    if density is not None:
        d["density"] = v(density, "kg/L")
    return d


@pytest.mark.parametrize("dose,flow,strength,kind,density,pump,expected,status", RULES_CASES)
def test_rules_md_cases(dose, flow, strength, kind, density, pump, expected, status):
    r = run_rule("R6", inputs(dose, flow, strength, kind, density, pump))
    assert r.status == status
    assert round(r.value, 2) == expected


def test_below_min_and_above_max_messages():
    assert "below pump minimum" in run_rule("R6", inputs(2, 500, 10, "w/v", None, (21.6, 444))).message
    assert "above pump maximum" in run_rule("R6", inputs(2, 500, 10, "w/w", 1.2, (0.5, 5))).message


def test_pump_min_at_tolerance_passes():
    # 0.36 L/min x 60 = 21.6 L/h: dose giving exactly 21.6 L/h passes
    r = run_rule("R6", {"dose": v(4.32, "mg/L"), "flow": v(500, "m3/h"), "strength": v(10, "% w/v"),
                        "pump_min": v(0.36, "L/min"), "pump_max": v(444, "L/h")})
    assert r.status == "OK"


def test_percent_without_kind_is_held():
    r = run_rule("R6", {**inputs(2, 500, 10, "w/v", None, (21.6, 444)), "strength": v(10, "%")})
    assert r.status == "held" and "strength" in r.message


def test_ww_without_density_is_held():
    r = run_rule("R6", inputs(2, 500, 10, "w/w", None, (0.5, 5)))
    assert r.status == "held" and "no default density" in r.message
