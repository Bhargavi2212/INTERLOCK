"""Drawing step in the pipeline with a fake models.see (no network)."""

import pymupdf
import pytest

from app.drawing.render import draw
from app.reading import longread, pipeline
from app.store.memory import MemoryStore
from tests.test_drawing_locate import WORDS
from tests.test_pipeline_fakes import CHANGE, PAGES, FakeModels

PNG = None


def page_png():
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1000, 700), False)
    pix.clear_with(255)
    return pix.tobytes("png")


def to_model(box, crop):
    """page box -> model box (yx, 0-1000) inside the crop, as the placeholder format expects."""
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    x0, y0, x1, y1 = ((box[0] - crop[0]) / cw, (box[1] - crop[1]) / ch, (box[2] - crop[0]) / cw, (box[3] - crop[1]) / ch)
    return [y0 * 1000, x0 * 1000, y1 * 1000, x1 * 1000]


class SeeModels(FakeModels):
    def __init__(self, fail=False, wrong_unit=False, **kw):
        super().__init__(**kw)
        self.fail, self.wrong_unit = fail, wrong_unit

    def see(self, role, prompt, png, schema, thinking="low", usage=None):
        if self.fail:
            raise RuntimeError("vision down")
        from app.drawing.locate import crop_window, find_anchor
        a = find_anchor(WORDS, ["floor wash water transfer pump"], "Unit-1")
        crop = crop_window(a["box"])
        item = [0.88, 0.70, 0.99, 0.80] if self.wrong_unit else [0.75, 0.70, 0.86, 0.80]
        label = [0.899, 0.779, 0.965, 0.79] if self.wrong_unit else [0.769, 0.779, 0.835, 0.79]
        nb = [0.599, 0.699, 0.616, 0.705]
        return {"found": True, "item_box": to_model(item, crop), "label_box": to_model(label, crop),
                "readings": [{"input": "line_nb", "value": "200", "unit": "NB", "label_text": "200NB",
                              "box": to_model(nb, crop), "role": "pump discharge"},
                             {"input": "shared_discharge", "value": "true", "label_text": "200NB",
                              "box": to_model(nb, crop)}],
                "why": "fake"}


@pytest.fixture
def plant():
    s = MemoryStore()
    p = s.create_plant("BHEL")
    pages = [dict(pg, is_drawing=(pg["file"] == "Part3.pdf")) for pg in PAGES]
    s.put_pages_all(p["plant_id"], pages)
    for pg in pages:
        s.put_page(p["plant_id"], pg["n"], {**pg, "words": WORDS if pg["is_drawing"] else []})
        if pg["is_drawing"]:
            s.put_page_png(p["plant_id"], pg["n"], page_png())
    s.mutate_plant(p["plant_id"], lambda d: d.update(page_count=len(pages), ingest_status="done"))
    longread._token_cache.clear()
    return s, p["plant_id"]


def run(plant, models):
    s, pid = plant
    return pipeline.check_change(s, models, pid, "c1", CHANGE)


def test_drawing_shared_header_makes_r1_ok(plant):
    res = run(plant, SeeModels())
    d = res["drawing"]
    assert d["found"] and d["verified"] and d["anchor"] == "text layer"
    ok = {r["input"]: r for r in d["readings"] if r["evidence_ok"]}
    assert {"line_nb", "shared_discharge", "line_role"} <= set(ok)
    r1 = next(r for r in res["results_after"] if r["rule_id"] == "R1")
    assert r1["status"] == "OK" and round(r1["value"], 2) == 1.86
    assert r1["notes"] and any("read from the drawing by Argon" in a for a in r1["assumptions"])
    assert r1["inputs"]["line_nb"]["source"] == "drawing"
    assert res["verdict"]["verdict"] == "BLOCK"
    assert plant[0].get_change_png("c1")[:8] == b"\x89PNG\r\n\x1a\n"


def test_look_alike_box_rejected_nothing_reaches_rules(plant):
    res = run(plant, SeeModels(wrong_unit=True))
    assert res["drawing"]["found"] is False and "unit tag" in res["drawing"]["check"]
    r1 = next(r for r in res["results_after"] if r["rule_id"] == "R1")
    assert r1["status"] == "held"


def test_drawing_failure_keeps_verdict(plant):
    res = run(plant, SeeModels(fail=True))
    step = next(s for s in res["steps"] if s["name"] == "drawing")
    assert step["state"].startswith("failed")
    assert res["drawing"]["found"] is False and res["verdict"]["verdict"] == "BLOCK"


def test_render_returns_png():
    out = draw(page_png(), {"crop_box": [0, 0, 1, 1], "item_box": [0.1, 0.1, 0.3, 0.3], "verified": True,
                            "readings": [{"input": "line_nb", "value": "200", "unit": "NB", "box": [0.5, 0.5, 0.6, 0.55],
                                          "evidence_ok": True}]})
    assert out[:8] == b"\x89PNG\r\n\x1a\n"


def test_drawing_route_needs_access_code(api, store):
    from fastapi.testclient import TestClient
    from app.api.main import app
    store.put_change("p", "c9", {"plant_id": "p", "drawing": {}})
    store.put_change_png("p", "c9", page_png())
    assert TestClient(app).get("/changes/c9/drawing.png").status_code == 401
    r = api.get("/changes/c9/drawing.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert api.get("/changes/nope/drawing.png").status_code == 404


class NoLineModels(SeeModels):
    def see(self, role, prompt, png, schema, thinking="low", usage=None):
        out = super().see(role, prompt, png, schema, thinking, usage)
        self.calls.append("see")
        out["readings"] = [r for r in out["readings"] if r["input"] not in ("line_nb", "shared_discharge")]
        return out


def test_no_line_in_crop_r1_held_one_call_only(plant):
    m = NoLineModels()
    res = run(plant, m)
    assert m.calls.count("see") == 1                       # no whole-sheet fallback call
    step = next(s for s in res["steps"] if s["name"] == "drawing")
    assert "no line size in the crop" in step["state"]
    r1 = next(r for r in res["results_after"] if r["rule_id"] == "R1")
    assert r1["status"] == "held"
