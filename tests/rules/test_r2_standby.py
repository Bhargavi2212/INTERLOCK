import pytest

from app.rules import run_rule
from tests.rules.conftest import v

# RULES.md R2 test cases: (installed, working, status)
RULES_CASES = [
    (2, 2, "flagged"),
    (3, 2, "OK"),
    (2, 1, "OK"),
]


@pytest.mark.parametrize("installed,working,status", RULES_CASES)
def test_rules_md_cases(installed, working, status):
    r = run_rule("R2", {"installed": v(installed, "count"), "working": v(working, "count")})
    assert r.status == status
    assert any("continuous duty assumed" in a for a in r.assumptions)
    assert r.limit_source.startswith("default")


def test_flagged_message():
    r = run_rule("R2", {"installed": v(2, "count"), "working": v(2, "count")})
    assert "installed 2 < working 2 + standby 1" in r.message


def test_arrangement_supplies_standby():
    r = run_rule("R2", {"installed": v(3, "count"), "working": v(2, "count"),
                        "arrangement": v("2W+1S")})
    assert r.status == "OK"
    assert "arrangement '2W+1S'" in r.limit_source
    assert not any("continuous duty" in a for a in r.assumptions)


def test_arrangement_supplies_working_only_when_missing():
    r = run_rule("R2", {"installed": v(2, "count"), "arrangement": v("1W+1S")})
    assert r.status == "OK"
    assert any("working count taken from the arrangement" in a for a in r.assumptions)


def test_working_input_wins_over_arrangement():
    # Scope page 1W+1S vs data sheet 2W: R2 uses working=2; the disagreement is the caller's.
    r = run_rule("R2", {"installed": v(2, "count"), "working": v(2, "count"),
                        "arrangement": v("1W+1S")})
    assert r.status == "flagged"


def test_bad_arrangement_is_held():
    r = run_rule("R2", {"installed": v(2, "count"), "working": v(1, "count"),
                        "arrangement": v("one plus one")})
    assert r.status == "held"
    assert "arrangement" in r.message


def test_installed_missing_is_held():
    r = run_rule("R2", {"working": v(2, "count")})
    assert r.status == "held"
    assert "installed" in r.message


def test_change_values_accepted():
    # The demo change: 2W+1S from the change text, installed 2 from the data sheet.
    r = run_rule("R2", {"installed": v(2, "count"), "working": v(2, "count", source="change"),
                        "arrangement": v("2W+1S", source="change")})
    assert r.status == "flagged"
    assert r.limit_source.startswith("default")  # standby never from the change


def test_change_3w_cannot_drop_standby():
    # installed 3, documents 2W+1S; change "3W": working 3, standby still 1 -> 3 < 4 flagged
    r = run_rule("R2", {"installed": v(3, "count"), "arrangement": v("2W+1S"),
                        "working": v(3, "count", source="change")})
    assert r.status == "flagged"
    r = run_rule("R2", {"installed": v(3, "count"), "arrangement": v("3W", source="change")})
    assert r.status == "flagged"
