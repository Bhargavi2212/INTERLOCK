from app.reading.scenario import build_scenario
from app.register.clash import find_clashes
from tests.test_scenario import CHANGE, SHARED, VALUES

UNDERSTANDING = {"item": "SG Unit-1 floor wash water transfer pumps", "names": ["floor wash pump"]}
REG = [{"entry_id": "reg-1", "item": "SG Unit-1 floor wash water transfer pumps",
        "attribute": "installed", "value": 3, "unit": "count"}]


def test_change_undoing_approved_value_clashes():
    # Later change: remove the third pump (installed 3 -> 2)
    changes = [{"input": "installed", "from": "3", "to": "2", "unit": "count"}]
    sc = build_scenario(VALUES, SHARED, changes, "remove the third pump", REG)
    clashes = find_clashes(REG, UNDERSTANDING, sc["after_values"])
    assert clashes == [{"entry_id": "reg-1", "attribute": "installed", "approved": 3, "proposed": "2"}]


def test_untouched_approved_value_does_not_clash():
    changes = [{"input": "flow_per_pump", "from": "105", "to": "110", "unit": "m3/h"}]
    sc = build_scenario(VALUES, SHARED, changes, "raise the flow", REG)
    assert find_clashes(REG, UNDERSTANDING, sc["after_values"]) == []


def test_different_item_no_clash():
    other = [{**REG[0], "item": "MRS Unit-1 waste water transfer pumps"}]
    changes = [{"input": "installed", "to": "2", "unit": "count"}]
    sc = build_scenario(VALUES, SHARED, changes, CHANGE, other)
    assert find_clashes(other, UNDERSTANDING, sc["after_values"]) == []


def test_empty_register_no_clash():
    sc = build_scenario(VALUES, SHARED, [], CHANGE)
    assert find_clashes([], UNDERSTANDING, sc["after_values"]) == []


U2 = {"item": "SG Unit-2 floor wash water transfer pumps", "names": ["floor wash pump"], "unit_tag": "Unit-2"}
REG_U1 = [{"entry_id": "reg-u1", "item": "SG Unit-1 floor wash water transfer pumps", "names": ["floor wash pump"],
           "attribute": "installed", "value": 3, "unit": "count"}]


def test_overlay_only_for_same_item_and_unit():
    changes = [{"input": "working", "to": "2", "unit": "count"}]
    sc_u2 = build_scenario(VALUES, SHARED, changes, "unit-2 change", REG_U1, understanding=U2)
    assert sc_u2["issued"]["R2"]["installed"].source == "document"        # Unit-1 approval not overlaid
    sc_u1 = build_scenario(VALUES, SHARED, changes, CHANGE, REG_U1, understanding={**UNDERSTANDING, "unit_tag": "Unit-1"})
    assert sc_u1["issued"]["R2"]["installed"].source == "register"


def test_unit1_approval_vs_unit2_change_no_clash():
    changes = [{"input": "installed", "to": "2", "unit": "count"}]
    sc = build_scenario(VALUES, SHARED, changes, "remove a unit-2 pump", REG_U1, understanding=U2)
    assert find_clashes(REG_U1, U2, sc["after_values"]) == []
    # the same change on Unit-1 does clash
    u1 = {**UNDERSTANDING, "unit_tag": "Unit-1"}
    sc1 = build_scenario(VALUES, SHARED, changes, "remove the third pump", REG_U1, understanding=u1)
    assert find_clashes(REG_U1, u1, sc1["after_values"])[0]["entry_id"] == "reg-u1"
