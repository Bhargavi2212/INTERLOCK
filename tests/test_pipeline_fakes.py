"""Whole pipeline with a fake models.py (no network)."""

import pytest

from app.reading import pipeline
from app.reading import longread
from app.reading.settings import reading_settings
from app.store.memory import MemoryStore

CHANGE = "SG Unit-1 floor wash water transfer pumps: go from 1 working + 1 standby to 2 working + 1 standby."
PAGES = [
    {"n": 0, "file": "Part1.pdf", "page": 43, "text": "SG UNIT-1 WASTE WATER TRANSFER PUMPS Two (1W+1S) nos."},
    {"n": 1, "file": "Part3.pdf", "page": 146, "text": "SG UNIT-1 FLR WASH WTR TRANSFER PUMPS 200NB\nSG UNIT-2 FLR WASH WTR"},
    {"n": 2, "file": "Part4.pdf", "page": 57, "text": "SG UNIT-1 FLOOR WASH WATER TRANSFER PUMPS\n"
        "Fluid to be handled Floor wash from ESP UNIT 1 containing ash traces\n"
        "Number required Two (2W) nos.\nRated capacity, each m3/ hr. 105\nEffective Capacity, m3 105 M3"},
    {"n": 3, "file": "Part5.pdf", "page": 200, "text": "Velocity of flow: pump discharge 50-150 mm 1.8-2.4 m/s; "
        "200 mm and above 2.1-2.5 m/s"},
    {"n": 4, "file": "Part4.pdf", "page": 58, "text": "ESP UNIT-2 FLOOR WASH WATER SUMP"},
]


class FakeModels:
    def __init__(self, decisions_fail=False, tokens=1000):
        self.decisions_fail, self.tokens, self.calls = decisions_fail, tokens, []

    def count_tokens(self, text):
        return self.tokens

    def decide(self, text, questions):
        self.calls.append("decisions")
        if self.decisions_fail:
            raise RuntimeError("decisions down")
        return {q: {"noul": 0.1 if "p.58" in text.split(f"[{q}]")[1][:40] else 0.9, "confidence": 0.9}
                for q in questions}

    def call(self, role, prompt, schema=None, thinking="low", usage=None):
        self.calls.append(role)
        assert thinking == "low"
        if role == "understand":
            return {"item": "SG Unit-1 floor wash water transfer pumps", "system": "SG Unit-1 floor wash",
                    "names": ["floor wash water transfer pumps", "FLR WASH WTR", "waste water transfer pumps"],
                    "unit_tag": "Unit-1", "is_pump_item": True,
                    "changes": [{"input": "working", "from": "1", "to": "2", "unit": "count"},
                                {"input": "arrangement", "from": "1W+1S", "to": "2W+1S", "unit": ""}]}
        if role == "long_read":
            assert prompt.startswith("=== Part1.pdf p.43 ===")  # pages block first (cache)
            if usage is not None:
                usage.update({"input": 1000, "cached": 900, "output": 50, "thought": 0})
            return {"pages": [{"file": "Part4.pdf", "page": 57, "why": "data sheet"},
                              {"file": "Nope.pdf", "page": 1, "why": "hallucinated"}]}
        if role == "values":
            assert "Fluid to be handled" in prompt and "(design basis)" in prompt
            q57 = lambda s: {"file": "Part4.pdf", "page": 57, "quote": s}
            return {"values": [
                {"input": "arrangement", "value": "1W+1S", "unit": "", "file": "Part1.pdf", "page": 43,
                 "quote": "SG UNIT-1 WASTE WATER TRANSFER PUMPS Two (1W+1S) nos."},
                {"input": "installed", "value": "2", "unit": "nos.", "file": "Part1.pdf", "page": 43,
                 "quote": "Two (1W+1S) nos."},
                {"input": "working", "value": "2", "unit": "nos.", **q57("Number required Two (2W) nos.")},
                {"input": "flow_per_pump", "value": "105", "unit": "m3/ hr.", **q57("Rated capacity, each m3/ hr. 105")},
                {"input": "volume", "value": "105", "unit": "m3", **q57("Effective Capacity, m3 105 M3")},
                {"input": "service", "value": "Floor wash from ESP UNIT 1 containing ash traces", "unit": "",
                 **q57("Fluid to be handled Floor wash from ESP UNIT 1 containing ash traces")},
                {"input": "line_nb", "value": "200", "unit": "NB", "file": "Part3.pdf", "page": 146, "quote": "200NB"},
                {"input": "flow_per_pump", "value": "999", "unit": "m3/h", **q57("Rated capacity 999 m3/h")},  # not on page
            ], "limits": [
                {"rule_id": "R1", "name": "velocity_band", "low": 1.8, "high": 2.4, "unit": "m/s",
                 "applies_from_nb": 50, "applies_to_nb": 150, "applies_to": "pump discharge",
                 "file": "Part5.pdf", "page": 200, "quote": "pump discharge 50-150 mm 1.8-2.4 m/s"},
                {"rule_id": "R1", "name": "velocity_band", "low": 2.1, "high": 2.5, "unit": "m/s",
                 "applies_from_nb": 200, "applies_to": "pump discharge",
                 "file": "Part5.pdf", "page": 200, "quote": "200 mm and above 2.1-2.5 m/s"},
            ], "shared_discharge": []}
        raise AssertionError(role)


@pytest.fixture
def plant():
    s = MemoryStore()
    p = s.create_plant("BHEL")
    s.put_pages_all(p["plant_id"], PAGES)
    s.mutate_plant(p["plant_id"], lambda d: d.update(page_count=len(PAGES), ingest_status="done"))
    longread._token_cache.clear()
    return s, p["plant_id"]


def run(plant, models, **kw):
    s, pid = plant
    return pipeline.check_change(s, models, pid, "c1", CHANGE, **kw)


def test_pipeline_end_to_end(plant):
    res = run(plant, FakeModels())
    assert [s["name"] for s in res["steps"]] == ["understand", "long_read", "search", "same_item", "values",
                                                 "drawing", "evidence", "rules", "clash", "verdict"]
    assert res["drawing"]["found"] is False and "no drawing page" in res["drawing"]["reason"]
    kept = {(p["file"], p["page"]) for p in res["pages"]}
    assert ("Part4.pdf", 57) in kept and ("Part3.pdf", 146) in kept and ("Part4.pdf", 58) not in kept
    assert all(p["file"] != "Nope.pdf" for p in res["pages"])          # hallucinated page dropped
    bad = [v for v in res["values"] if not v["evidence_ok"]]
    assert [v["value"] for v in bad] == ["999"]                         # struck through, never used
    after = {r["rule_id"]: r for r in res["results_after"]}
    assert after["R1"]["status"] == "held"                              # no shared discharge in text (A1)
    assert "do not state in text whether the pumps share one discharge line" in after["R1"]["message"]
    assert after["R2"]["status"] == "flagged" and after["R3"]["status"] == "held"
    assert any(d["attribute"] == "working" for d in res["disagreements"])
    assert res["verdict"]["verdict"] == "BLOCK"
    assert res["page_count"] == len(PAGES) and res["same_item_mode"] == "decisions"
    basis = [p for p in res["pages"] if p["found_by"] == "design basis"]
    assert [(p["file"], p["page"]) for p in basis] == [("Part5.pdf", 200)]


def test_decisions_failure_falls_back_to_names(plant):
    res = run(plant, FakeModels(decisions_fail=True))
    assert res["same_item_mode"] == "names" and "Decisions API failed" in res["same_item_note"]
    assert res["verdict"]["verdict"] == "BLOCK"


def test_long_read_skipped_over_limit(plant):
    limit = reading_settings()["long_read"]["token_limit"]
    m = FakeModels(tokens=limit + 1)
    res = run(plant, m)
    assert res["long_read"] == "skipped: over limit" and "long_read" not in m.calls
    assert f"{limit:,}" in res["long_read_message"]


def test_explain_failure_keeps_verdict(plant):
    def boom(*a):
        raise RuntimeError("carbon down")
    res = run(plant, FakeModels(), explain_fn=boom, headlines_fn=lambda after, d, c: ["h"])
    assert res["explanations"] == [{"note": "explanation unavailable"}]
    assert res["headlines"] == ["h"] and res["verdict"]["verdict"] == "BLOCK"
    names = [s["name"] for s in res["steps"]]
    assert names.index("explain") < names.index("verdict")


def test_long_read_prompt_byte_identical(plant):
    s, pid = plant
    assert longread.pages_block(s.get_pages_all(pid)) == longread.pages_block(s.get_pages_all(pid))


def test_token_count_stored_on_plant_once(plant):
    s, pid = plant

    class Counting(FakeModels):
        n = 0

        def count_tokens(self, text):
            Counting.n += 1
            return 1234

    run(plant, Counting())
    assert s.get_plant(pid)["token_count"] == {"value": 1234, "estimated": False}
    longread._token_cache.clear()            # a new process: memory cache empty
    res = run(plant, Counting())
    assert Counting.n == 1                   # not recounted: read from the plant
    assert res["long_read_usage"]["cached"] == 900
