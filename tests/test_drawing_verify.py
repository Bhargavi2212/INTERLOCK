from app.drawing.verify import check_item, check_reading, line_role_values
from app.reading.scenario import build_scenario
from app.rules import run_rules
from app.rules.model import Value
from tests.rules.conftest import bhel_bands
from tests.test_drawing_locate import WORDS

U1 = {"item": "SG Unit-1 floor wash water transfer pumps", "names": ["floor wash water transfer pump"],
      "unit_tag": "Unit-1"}
U1_LABEL = [0.769, 0.779, 0.835, 0.79]       # around the SG UNIT-1 label words
U2_LABEL = [0.899, 0.779, 0.965, 0.79]
NB200 = [0.779, 0.739, 0.796, 0.745]


def test_item_box_with_label_and_unit_tag_passes():
    ok, why = check_item(WORDS, [0.75, 0.70, 0.86, 0.80], U1_LABEL, U1)
    assert ok, why


def test_item_box_on_look_alike_fails():
    ok, why = check_item(WORDS, [0.88, 0.70, 0.99, 0.80], U2_LABEL, U1)
    assert not ok and "unit tag" in why


def test_no_text_layer_not_verifiable():
    ok, why = check_item([], [0.1, 0.1, 0.2, 0.2], [0.1, 0.1, 0.2, 0.2], U1)
    assert not ok and "no text layer" in why
    r = check_reading({"input": "line_nb", "value": "200", "unit": "NB", "label_text": "200NB", "box": NB200},
                      [], "Part3.pdf", 146)
    assert not r["evidence_ok"] and "no text layer" in r["evidence_reason"]


def test_reading_label_inside_box_passes():
    r = check_reading({"input": "line_nb", "value": "200", "unit": "NB", "label_text": "200NB",
                       "box": NB200, "role": "discharge header"}, WORDS, "Part3.pdf", 146)
    assert r["evidence_ok"], r["evidence_reason"]
    assert r["source"] == "drawing" and r["box"] == tuple(NB200)
    assert line_role_values([r])[0]["value"] == "discharge header"


def test_reading_label_outside_box_fails():
    r = check_reading({"input": "line_nb", "value": "200", "unit": "NB", "label_text": "200NB",
                       "box": [0.1, 0.1, 0.2, 0.2]}, WORDS, "Part3.pdf", 146)
    assert not r["evidence_ok"] and "not inside the box" in r["evidence_reason"]


def test_reading_value_not_in_label_fails():
    r = check_reading({"input": "line_nb", "value": "150", "unit": "NB", "label_text": "200NB", "box": NB200},
                      WORDS, "Part3.pdf", 146)
    assert not r["evidence_ok"] and "not in the label" in r["evidence_reason"]


def test_shared_discharge_needs_label_only_and_states_assumption():
    r = check_reading({"input": "shared_discharge", "value": True, "label_text": "200NB", "box": NB200},
                      WORDS, "Part3.pdf", 146)
    assert r["evidence_ok"] and "read from the drawing by Argon" in r["assumption"]


def test_engine_holds_unverified_drawing_value():
    from app.rules import run_rule
    bad = Value(200, "NB", file="Part3.pdf", page=146, quote="200NB", evidence_ok=False, source="drawing",
                box=(0.1, 0.1, 0.2, 0.2))
    r = run_rule("R1", {"flow_total": Value(105, "m3/h", file="a.pdf", page=1, quote="105"), "line_nb": bad})
    assert r.status == "held" and "evidence check failed" in r.message and "(drawing)" in r.message


def d(input, value, unit, file, page, source="document", box=None):
    return {"input": input, "value": value, "unit": unit, "file": file, "page": page, "quote": f"{value}{unit}",
            "evidence_ok": True, "source": source, "box": box}


def test_a3_regression_text_label_dropped_drawing_value_kept():
    """EVAL.md section 6, A3: a bare '65NB' in the drawing's text layer must not reach R1."""
    vals = [d("flow_per_pump", "20", "m3/h", "Part4.pdf", 56), d("working", "1", "count", "Part4.pdf", 56),
            d("line_nb", "65", "NB", "Part3.pdf", 146),                                       # text layer
            d("line_nb", "50", "NB", "Part3.pdf", 146, source="drawing", box=(0.3, 0.7, 0.31, 0.71))]
    sc = build_scenario(vals, [], [], "", drawing_pages={("Part3.pdf", 146)})
    line = sc["issued"]["R1"]["line_nb"]
    assert line.value == "50" and line.source == "drawing" and line.box == (0.3, 0.7, 0.31, 0.71)
    r1 = next(r for r in run_rules(sc["issued"], bhel_bands()) if r.rule_id == "R1")
    assert r1.status == "flagged" and round(r1.value, 2) == 2.83


def test_text_shared_discharge_on_drawing_page_dropped():
    shared_text = [{"value": True, "file": "Part3.pdf", "page": 146, "quote": "x", "evidence_ok": True}]
    sc = build_scenario([d("working", "2", "count", "Part4.pdf", 57)], shared_text, [], "",
                        drawing_pages={("Part3.pdf", 146)})
    assert sc["shared_discharge"] is None


def test_line_label_must_be_nearest_to_this_items_label():
    from app.drawing.locate import find_anchor
    from app.drawing.verify import check_line_near_item
    a1 = find_anchor(WORDS, ["floor wash water transfer pump"], "Unit-1")
    u1_nb = [0.779, 0.739, 0.796, 0.745]          # 200NB printed by the SG Unit-1 pumps
    u2_nb = [0.909, 0.739, 0.926, 0.745]          # 200NB printed by the SG Unit-2 pumps
    good = check_reading({"input": "line_nb", "value": "200", "unit": "NB", "label_text": "200NB", "box": u1_nb},
                         WORDS, "Part3.pdf", 146)
    bad = check_reading({"input": "shared_discharge", "value": "true", "label_text": "200NB", "box": u2_nb},
                        WORDS, "Part3.pdf", 146)
    assert good["evidence_ok"] and bad["evidence_ok"]           # both labels really say 200NB
    out = check_line_near_item([good, bad], WORDS, a1)
    assert out[0]["evidence_ok"] and "this item's" in out[0]["evidence_reason"]
    assert not out[1]["evidence_ok"] and "SG UNIT-2" in out[1]["evidence_reason"]
    assert "assumption" not in out[1]


def test_line_reading_without_anchor_fails():
    from app.drawing.verify import check_line_near_item
    r = check_reading({"input": "line_nb", "value": "200", "unit": "NB", "label_text": "200NB",
                       "box": [0.779, 0.739, 0.796, 0.745]}, WORDS, "Part3.pdf", 146)
    assert not check_line_near_item([r], WORDS, None)[0]["evidence_ok"]
