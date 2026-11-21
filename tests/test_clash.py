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
