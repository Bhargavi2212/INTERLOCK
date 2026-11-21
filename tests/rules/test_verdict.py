import json

import pytest

from app.rules import run_rule, run_rules
from app.rules.model import RuleResult
from app.verdict import BLOCK, NO_CONFLICTS, REVIEW, VERDICTS, proven, verdict
from tests.rules.conftest import bhel_bands, v

EVAL_EXPECTED_VERDICTS = {"BLOCK", "REVIEW", "no conflicts found"}  # EVAL.md §2


def rr(rule_id, status, notes=None):
    return RuleResult(rule_id=rule_id, status=status, value=None, unit="", limit=None,
                      limit_source="", formula="", inputs={}, message=f"{rule_id} {status}",
                      notes=notes or [])


DISAGREE = [{"attribute": "working pumps", "values": [
    {"file": "Part1.pdf", "page": 4, "value": "1W+1S"}, {"file": "Part4.pdf", "page": 59, "value": "2W"}]}]
CLASH = [{"entry_id": "reg-1", "attribute": "discharge header NB", "approved": 200, "proposed": 100}]


def test_verdict_strings_match_eval_keys():
    assert set(VERDICTS) == EVAL_EXPECTED_VERDICTS


@pytest.mark.parametrize("results,dis,clash,expected", [
    ([rr("R1", "flagged")], [], [], BLOCK),
    ([rr("R1", "OK")], DISAGREE, [], BLOCK),
    ([rr("R1", "OK")], [], CLASH, BLOCK),
    ([rr("R1", "flagged"), rr("R3", "held")], [], [], BLOCK),
    ([rr("R1", "OK"), rr("R3", "held")], [], [], REVIEW),
    ([rr("R1", "OK"), rr("R2", "OK")], [], [], NO_CONFLICTS),
    ([], [], [], NO_CONFLICTS),
])
def test_verdict(results, dis, clash, expected):
    out = verdict(results, dis, clash, pages_read=851)
    assert out["verdict"] == expected


def test_no_conflicts_label_has_page_count():
    out = verdict([rr("R1", "OK")], [], [], pages_read=805, pages_unreadable=46)
    assert out["label"] == "No conflicts found in 805 pages read (46 pages had no readable text)"


def test_reasons_list_everything():
    out = verdict([rr("R1", "flagged"), rr("R3", "held")], DISAGREE, CLASH, 10)
    text = " ".join(out["reasons"])
    assert "R1 flagged" in text and "R3 held" in text
    assert "Part1.pdf p.4" in text and "reg-1" in text


def test_pass_never_appears():
    for results, dis, clash in [([rr("R1", "OK")], [], []), ([rr("R1", "held")], [], []),
                                ([rr("R1", "flagged")], DISAGREE, CLASH)]:
        out = json.dumps(verdict(results, dis, clash, 5)) + json.dumps(proven(results, results, clash))
        assert "PASS" not in out


def test_proven_allows_preexisting_held():
    assert proven([rr("R3", "held")], [rr("R1", "OK"), rr("R3", "held")], [])["proven"]


def test_proven_refuses_new_held():
    out = proven([rr("R3", "OK")], [rr("R3", "held")], [])
    assert not out["proven"] and "newly held" in out["reasons"][0]


def test_proven_refuses_flagged():
    assert not proven([], [rr("R1", "flagged")], [])["proven"]


def test_proven_refuses_clash():
    assert not proven([], [rr("R1", "OK")], CLASH)["proven"]


def test_proven_ignores_notes():
    assert proven([], [rr("R1", "OK", notes=["below the documents' lower value"])], [])["proven"]


def test_demo_case_end_to_end():
    """PROJECT.md section 4 (200 NB, as the P&ID shows): BLOCK from the disagreement and R2;
    the third-pump fix is proven; a later change removing it clashes with the register."""
    bands = bhel_bands()
    sump = {"volume": v(105, "m3"), "q_out": v(210, "m3/h")}  # inflow not stated -> held
    change = {
        "R1": {"flow_per_pump": v(105, "m3/h"), "pumps_into_line": v(2, "count", source="change"),
               "line_nb": v(200, "NB")},
        "R2": {"installed": v(2, "count"), "arrangement": v("2W+1S", source="change")},
        "R3": sump,
    }
    before = run_rules(change, bands)
    assert {r.rule_id: r.status for r in before} == {"R1": "OK", "R2": "flagged", "R3": "held"}
    assert round(before[0].value, 2) == 1.86
    assert any("information" in n or "lower value" in n for n in before[0].notes)
    assert verdict(before, DISAGREE, [], 851)["verdict"] == BLOCK
    assert verdict(before, [], [], 851)["verdict"] == BLOCK  # R2 alone also blocks

    fix = {**change, "R2": {**change["R2"], "installed": v(3, "count", source="fix")}}
    after = run_rules(fix, bands)
    assert {r.rule_id: r.status for r in after} == {"R1": "OK", "R2": "OK", "R3": "held"}
    assert proven(before, after, [])["proven"]

    # Later change removing the third pump: clash with the approved register entry -> BLOCK
    clash = [{"entry_id": "reg-1", "attribute": "installed pumps", "approved": 3, "proposed": 2}]
    later = run_rules(change, bands)
    assert verdict(later, [], clash, 851)["verdict"] == BLOCK
    assert any("reg-1" in r for r in verdict(later, [], clash, 851)["reasons"])


def test_rule_results_serialise():
    r = run_rule("R1", {"flow_total": v(105, "m3/h"), "line_nb": v(100, "NB")}, bhel_bands())
    json.dumps(r.to_dict())


def test_proven_refuses_rule_missing_after_fix():
    out = proven([rr("R1", "flagged"), rr("R3", "held")], [rr("R1", "OK")], [])
    assert not out["proven"] and any("R3 was not re-run" in r for r in out["reasons"])
