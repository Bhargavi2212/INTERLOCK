import pytest

from app.rules import run_rule
from tests.rules.conftest import v

# RULES.md R4 test cases: (operating, set, design bar(g), status, phrase in message)
RULES_CASES = [
    (30, 22, 40, "flagged", "lifts"),
    (30, 35, 40, "OK", ""),
    (30, 32, 40, "flagged", "simmers"),
    (30, 45, 40, "flagged", "above design"),
]


@pytest.mark.parametrize("op,set_p,design,status,phrase", RULES_CASES)
def test_rules_md_cases(op, set_p, design, status, phrase):
    r = run_rule("R4", {"operating": v(op, "bar(g)"), "set": v(set_p, "bar(g)"),
                        "design": v(design, "bar(g)")})
    assert r.status == status
    assert phrase in r.message


def test_absolute_pressure_converted():
    # 31.013 bar a = 30 bar(g); set 35 -> OK
    r = run_rule("R4", {"operating": v(31.013, "bar a"), "set": v(35, "bar(g)"),
                        "design": v(40, "bar(g)")})
    assert r.status == "OK"
    assert any("absolute" in a for a in r.assumptions)


def test_missing_set_is_held():
    r = run_rule("R4", {"operating": v(30, "bar(g)"), "design": v(40, "bar(g)")})
    assert r.status == "held" and "set" in r.message
