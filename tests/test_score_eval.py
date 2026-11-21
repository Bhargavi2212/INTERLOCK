"""score_eval.py: pure scoring code (no network, no model)."""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_eval as se  # noqa: E402

KEY = {"id": "E9", "expected_verdict": "BLOCK",
       "expected_pages": [{"file": "Part1.pdf", "page": 43}, {"file": "Part5.pdf", "page": 200}],
       "expected_values": [{"file": "Part1.pdf", "page": 43, "value": "2", "unit": "count"}]}


def out(pages, values=(), verdict="BLOCK"):
    return {"pages": list(pages), "values": list(values), "verdict": {"verdict": verdict}}


def test_basename_matching():
    o = out([{"file": "bhel/Part1.pdf", "page": 43}, {"file": "x/y/Part5.pdf", "page": 200}])
    s = se.score_run("one_call", KEY, o, {})
    assert s["recall"] == 1.0 and s["wrong"] == []


def test_design_basis_counts_for_recall_never_wrong():
    o = out([{"file": "Part1.pdf", "page": 43}, {"file": "Part5.pdf", "page": 200, "found_by": "design basis"},
             {"file": "Part4.pdf", "page": 9, "found_by": "design basis"}])
    s = se.score_run("interlock", KEY, o, {})
    assert s["recall"] == 1.0          # key lists Part5 p.200
    assert s["wrong"] == []            # Part4 p.9 is design basis: not wrong


def test_value_on_wrong_page_not_matched():
    right = {"file": "Part1.pdf", "page": 43, "value": "2W+1S", "unit": "", "evidence_ok": True}
    wrong = dict(right, page=44)
    assert se.score_run("interlock", KEY, out([], [right]), {})["values"] == 1.0
    assert se.score_run("interlock", KEY, out([], [wrong]), {})["values"] == 0.0


def test_interlock_values_need_evidence_ok():
    v = {"file": "Part1.pdf", "page": 43, "value": "2", "unit": "count", "evidence_ok": False}
    assert se.score_run("interlock", KEY, out([], [v]), {})["values"] == 0.0
    assert se.score_run("one_call", KEY, out([], [v]), {})["values"] == 1.0


def test_units_and_ranges():
    kv = {"file": "a.pdf", "page": 1, "value": "2.1-2.5", "unit": "m/s"}
    assert se.value_matches(kv, {"file": "a.pdf", "page": 1, "value": "2.1 - 2.5", "unit": "m/sec"})
    km = {"file": "a.pdf", "page": 1, "value": "545", "unit": "m"}
    assert se.value_matches(km, {"file": "a.pdf", "page": 1, "value": "545", "unit": "m"})


def write_run(d: Path, name, started, output, seconds=10.0):
    (d / name).write_text(json.dumps({"started_at": started, "seconds": seconds, "state": "done",
                                      "output": output}), encoding="utf-8")


def test_worst_of_three_and_key_before_run(tmp_path):
    full = out([{"file": "Part1.pdf", "page": 43}, {"file": "Part5.pdf", "page": 200}])
    half = out([{"file": "Part1.pdf", "page": 43}], verdict="REVIEW")
    write_run(tmp_path, "E_E9_interlock_1.json", "2026-11-21T14:00:00", full)
    write_run(tmp_path, "E_E9_interlock_2.json", "2026-11-21T14:10:00", half)
    write_run(tmp_path, "E_E9_interlock_3.json", "2026-11-21T12:00:00", full)   # older than the key
    s = se.score_dir(tmp_path, {"E9": KEY}, {}, {"E9": datetime(2026, 11, 21, 13, 0)})
    m = s["systems"]["interlock"]["E"]
    assert m["page_recall_worst"]["E9"] == 0.5
    assert m["page_recall_spread"]["E9"] == [0.5, 1.0]
    assert m["verdict_matches"] == [2, 3]
    flags = {k["file"]: k["ok"] for k in s["key_before_run"]}
    assert flags == {"E_E9_interlock_1.json": True, "E_E9_interlock_2.json": True, "E_E9_interlock_3.json": False}
    assert s["time"]["cold_started"] == "2026-11-21T12:00:00"


def test_run_f_code_math_matches_f_keys():
    import run_f
    for kid, (val, status) in {"F1": (1.86, "OK"), "F2": (30.0, "held"), "F3": (3, "OK")}.items():
        key = json.loads((ROOT / "eval" / "keys" / f"{kid}.json").read_text(encoding="utf-8"))
        o = run_f.interlock(key)
        assert o["status"] == status and abs(o["value"] - val) <= 0.01 * val
    f1 = run_f.interlock(json.loads((ROOT / "eval" / "keys" / "F1.json").read_text(encoding="utf-8")))
    assert f1["limit"] == 2.5 and f1["doc_limits"][0]["applies_to"] == "pump discharge"   # G2: band, not 3.0
