import pytest

from app.rules import run_rule
from tests.rules.conftest import v

# RULES.md R3 test cases: (V m3, Q_out m3/h, Q_in m3/h or None, expected cycle min or None, status)
RULES_CASES = [
    (105, 210, None, None, "held"),
    (105, 210, 100, 120.3, "OK"),
    (10, 60, 50, 72.0, "OK"),
    (2, 60, 30, 8.0, "flagged"),
    (10, 60, 60, None, "flagged"),
]


@pytest.mark.parametrize("vol,q_out,q_in,expected,status", RULES_CASES)
def test_rules_md_cases(vol, q_out, q_in, expected, status):
    inputs = {"volume": v(vol, "m3"), "q_out": v(q_out, "m3/h")}
    if q_in is not None:
        inputs["q_in"] = v(q_in, "m3/h")
    r = run_rule("R3", inputs)
    assert r.status == status
    if expected is not None:
        assert round(r.value, 1) == expected


def test_held_shows_pump_out_time():
    r = run_rule("R3", {"volume": v(105, "m3"), "q_out": v(210, "m3/h")})
    assert any("pump-out only 30.0 min" in n for n in r.notes)
    assert "q_in" in r.message


def test_cannot_keep_up_message():
    r = run_rule("R3", {"volume": v(10, "m3"), "q_out": v(60, "m3/h"), "q_in": v(60, "m3/h")})
    assert "cannot keep up" in r.message
    assert r.value is None


@pytest.mark.parametrize("name", ["q_in", "q_out"])
def test_non_positive_flow_is_held(name):
    inputs = {"volume": v(10, "m3"), "q_out": v(60, "m3/h"), "q_in": v(30, "m3/h")}
    inputs[name] = v(0, "m3/h")
    r = run_rule("R3", inputs)
    assert r.status == "held"
    assert name in r.message


def test_total_volume_assumption():
    r = run_rule("R3", {"volume": v(10, "m3"), "q_out": v(60, "m3/h"), "q_in": v(50, "m3/h"),
                        "volume_is_total": v(True)})
    assert any("total volume used as working volume" in a for a in r.assumptions)
