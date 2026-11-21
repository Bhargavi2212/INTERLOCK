import pytest

from app.rules import run_rule
from tests.rules.conftest import v

# RULES.md R5 test cases: (inputs, required bar(g), status)
RULES_CASES = [
    ({"operating": 5.0, "design": 6.0}, 6.0, "OK"),
    ({"operating": 5.0, "design": 5.5}, 6.0, "flagged"),
    ({"max_suction": 0.5, "shutoff_head": 9.0, "design": 8.0}, 9.5, "flagged"),
]


@pytest.mark.parametrize("given,required,status", RULES_CASES)
def test_rules_md_cases(given, required, status):
    r = run_rule("R5", {k: v(x, "bar(g)") for k, x in given.items()})
    assert r.status == status
    assert round(r.limit, 2) == required


def test_head_water_service_uses_sg_one():
    # 90 m x 0.0981 x 1.0 = 8.829 bar; + 0.5 = 9.329 <= design 10 -> OK
    r = run_rule("R5", {"max_suction": v(0.5, "bar(g)"), "shutoff_head": v(90, "m"),
                        "design": v(10, "bar(g)"), "service": v("clarified water")})
    assert r.status == "OK"
    assert round(r.limit, 2) == 9.33
    assert any("SG 1.0" in a for a in r.assumptions)


def test_sludge_water_is_held():
    r = run_rule("R5", {"max_suction": v(0.5, "bar(g)"), "shutoff_head": v(90, "m"),
                        "design": v(10, "bar(g)"), "service": v("sludge water")})
    assert r.status == "held" and "sg" in r.message


def test_head_without_service_is_held():
    r = run_rule("R5", {"max_suction": v(0.5, "bar(g)"), "shutoff_head": v(90, "m"),
                        "design": v(10, "bar(g)")})
    assert r.status == "held" and "service not stated" in r.message


def test_stated_sg_used():
    r = run_rule("R5", {"max_suction": v(0.5, "bar(g)"), "shutoff_head": v(90, "m"),
                        "design": v(10, "bar(g)"), "sg": v(1.2, ""), "service": v("slurry")})
    assert round(r.limit, 2) == round(0.5 + 90 * 0.0981 * 1.2, 2)


def test_pump_basis_wins_over_margin():
    r = run_rule("R5", {"max_suction": v(0.5, "bar(g)"), "shutoff_head": v(9.0, "bar(g)"),
                        "operating": v(5.0, "bar(g)"), "design": v(8.0, "bar(g)")})
    assert r.status == "flagged" and "pump basis" in r.message


def test_neither_basis_is_held():
    r = run_rule("R5", {"design": v(8.0, "bar(g)")})
    assert r.status == "held"
