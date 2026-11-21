"""Score the committed eval runs (PHASE_5 spec + Amendments). Pure code: no model calls, no network.

    python scripts/score_eval.py            # scores eval/results (first runs) and eval/results/rerun
Writes eval/results/scores.json and prints markdown tables and every miss.

Rules (EVAL.md section 1, PHASE_5): same scoring for every system; pages by file basename + page;
design-basis pages count toward recall when the key lists them and never as wrong pages;
Interlock values count only if evidence_ok; value matching is generous (any key number found in
the returned value, units compatible) and stated so in EVAL.md section 4; set E worst of 3 per change.
Keys must be committed before each scored run (checked and printed).
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.reading.evidence import numbers, quote_on_page  # noqa: E402
from app.rules.engine import load_rules  # noqa: E402
from app.rules.units import UnknownUnit, counts_in_text, normalise, to_base  # noqa: E402

QUANTITIES = ("flow", "volume", "nb", "diameter", "pressure", "velocity", "count", "concentration", "density")


# ---------------------------------------------------------------- helpers

def base(f) -> str:
    return Path(str(f)).name


def page_key(p) -> tuple[str, int]:
    return base(p["file"]), int(p["page"])


def key_commit_time(path: Path, root: Path = ROOT) -> datetime | None:
    out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(path.relative_to(root))],
                         cwd=root, capture_output=True, text=True)
    s = out.stdout.strip()
    return datetime.fromisoformat(s).astimezone().replace(tzinfo=None) if s else None


def units_compatible(ku: str, su: str) -> bool:
    ku, su = (ku or "").strip(), (su or "").strip()
    if not ku or normalise(ku) in ("count",) or normalise(ku) == normalise(su):
        return True
    cfg = load_rules()["units"]
    for q in QUANTITIES:
        try:
            to_base(q, 1, ku, cfg)
            to_base(q, 1, su or "count", cfg)
            return True
        except UnknownUnit:
            continue
    return False


def value_matches(kv: dict, sv: dict) -> bool:
    """Generous: same file+page, every number of the key value found in the returned value
    (numbers, or counts incl. words/arrangement totals), units compatible."""
    if page_key(kv) != page_key(sv):
        return False
    k_nums = numbers(str(kv["value"]))
    if not k_nums:
        return str(kv["value"]).strip().lower() in str(sv.get("value", "")).lower()
    s_text = f"{sv.get('value', '')}"
    s_nums = numbers(s_text) | counts_in_text(s_text, load_rules()["units"])
    return k_nums <= s_nums and units_compatible(kv.get("unit", ""), sv.get("unit", ""))


# ---------------------------------------------------------------- per-run extraction

def run_pages(system: str, out: dict) -> tuple[set, set]:
    """-> (pages returned, design-basis pages) as {(basename, page)}."""
    pages = {page_key(p) for p in out.get("pages", []) if "file" in p and "page" in p}
    basis = {page_key(p) for p in out.get("pages", []) if p.get("found_by") == "design basis"}
    return pages, basis


def run_values(system: str, out: dict) -> list[dict]:
    vals = out.get("values", []) or []
    if system == "interlock":
        return [v for v in vals if v.get("evidence_ok")]
    return [v for v in vals if "file" in v and "page" in v]


def run_verdict(system: str, out: dict) -> str | None:
    v = out.get("verdict")
    return v.get("verdict") if isinstance(v, dict) else v


def score_run(system: str, key: dict, out: dict, page_texts: dict) -> dict:
    kp = {page_key(p) for p in key.get("expected_pages", [])}
    got, basis = run_pages(system, out)
    found = got & kp
    wrong = sorted(got - kp - basis)
    kvals = key.get("expected_values", [])
    svals = run_values(system, out)
    matched = sum(1 for kv in kvals if any(value_matches(kv, sv) for sv in svals))
    if system == "interlock":
        all_vals = out.get("values", []) or []
        evid = (sum(1 for v in all_vals if v.get("evidence_ok")), len(all_vals))
    elif system == "one_call":
        ok = 0
        for v in svals:
            text = page_texts.get(page_key(v))
            ok += bool(text and quote_on_page(v.get("quote", ""), text)[0])
        evid = (ok, len(svals))
    else:
        evid = None
    return {"recall": len(found) / len(kp) if kp else None, "missing": sorted(kp - got), "wrong": wrong,
            "values": matched / len(kvals) if kvals else None, "evidence": evid,
            "verdict": run_verdict(system, out), "verdict_ok": run_verdict(system, out) == key.get("expected_verdict")}


def same_item(out: dict, key: dict) -> tuple[int, int, int]:
    """(true positives kept, kept, key pages among candidates) over non-design-basis candidates."""
    kp = {page_key(p) for p in key.get("expected_pages", [])}
    kept = {page_key(p) for p in out.get("pages", []) if p.get("found_by") != "design basis"}
    rejected = {page_key(p) for p in out.get("pages_rejected", [])}
    cand = kept | rejected
    return len(kept & kp), len(kept), len(cand & kp)


# ---------------------------------------------------------------- the whole score

def load_page_texts() -> dict:
    texts = {}
    folder = ROOT / "data" / "bhel"
    try:
        import pymupdf
        for pdf in sorted(folder.glob("*.pdf")):
            with pymupdf.open(pdf) as doc:
                for i, page in enumerate(doc, start=1):
                    texts[(pdf.name, i)] = page.get_text()
    except Exception:  # noqa: BLE001  (no PDFs: one-call evidence reported as n/a)
        pass
    return texts


def score_dir(results: Path, keys: dict, page_texts: dict, key_times: dict) -> dict:
    out = {"systems": {}, "misses": [], "key_before_run": [], "time": {}, "same_item": None, "drawing": None}
    files = sorted(results.glob("[EA]_*_*_*.json"))
    per = {}
    starts = []
    for f in files:
        set_name, kid, system, run = f.stem.split("_", 3)[0], f.stem.split("_")[1], "_".join(f.stem.split("_")[2:-1]), int(f.stem.split("_")[-1])
        if kid not in keys:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        started = datetime.fromisoformat(d["started_at"])
        kt = key_times.get(kid)
        out["key_before_run"].append({"file": f.name, "key_committed": kt.isoformat() if kt else None,
                                      "run_started": d["started_at"], "ok": bool(kt and kt < started)})
        if d.get("state") != "done" or not isinstance(d.get("output"), dict):
            out["misses"].append({"set": set_name, "id": kid, "system": system, "run": run, "failed": d.get("error")})
            continue
        s = score_run(system, keys[kid], d["output"], page_texts)
        s.update(seconds=d["seconds"], started=d["started_at"], run=run)
        per.setdefault((set_name, system), {}).setdefault(kid, []).append(s)
        if system == "interlock":
            starts.append((d["started_at"], d["seconds"]))
        if s["missing"] or s["wrong"] or not s["verdict_ok"]:
            out["misses"].append({"set": set_name, "id": kid, "system": system, "run": run,
                                  "missing_pages": s["missing"], "wrong_pages": s["wrong"],
                                  "verdict": s["verdict"], "expected": keys[kid].get("expected_verdict")})

    for (set_name, system), by_key in per.items():
        recalls = {k: min(r["recall"] for r in rs) for k, rs in by_key.items()}
        spread = {k: [min(r["recall"] for r in rs), max(r["recall"] for r in rs)] for k, rs in by_key.items()}
        wrong = {k: max(len(r["wrong"]) for r in rs) for k, rs in by_key.items()}
        vals = {k: min(r["values"] for r in rs if r["values"] is not None) for k, rs in by_key.items()
                if any(r["values"] is not None for r in rs)}
        ev = [r["evidence"] for rs in by_key.values() for r in rs if r["evidence"]]
        verdicts = [r["verdict_ok"] for rs in by_key.values() for r in rs]
        secs = [r["seconds"] for rs in by_key.values() for r in rs]
        out["systems"].setdefault(system, {})[set_name] = {
            "page_recall_worst_mean": round(statistics.mean(recalls.values()), 3), "page_recall_worst": recalls,
            "page_recall_spread": spread, "wrong_pages_worst": wrong, "wrong_pages_sum": sum(wrong.values()),
            "value_accuracy_worst_mean": round(statistics.mean(vals.values()), 3) if vals else None,
            "evidence": [sum(a for a, _ in ev), sum(b for _, b in ev)] if ev else None,
            "verdict_matches": [sum(verdicts), len(verdicts)],
            "seconds_median": round(statistics.median(secs), 1), "seconds_max": max(secs), "runs": len(secs)}

    a_runs = per.get(("A", "interlock"), {})
    if a_runs:
        tp = kept = keyc = 0
        for kid, rs in a_runs.items():
            for r_file in sorted(results.glob(f"A_{kid}_interlock_*.json")):
                o = json.loads(r_file.read_text(encoding="utf-8")).get("output") or {}
                a, b, c = same_item(o, keys[kid])
                tp, kept, keyc = tp + a, kept + b, keyc + c
        out["same_item"] = {"precision": round(tp / kept, 3) if kept else None,
                            "recall": round(tp / keyc, 3) if keyc else None, "kept": kept, "key_candidates": keyc}

    if starts:
        starts.sort()
        warm = [s for _, s in starts[1:]]
        out["time"] = {"cold_first_run_s": starts[0][1], "cold_started": starts[0][0],
                       "warm_median_s": round(statistics.median(warm), 1) if warm else None}

    b_files = sorted(results.glob("B_all_interlock_*.json"))
    if b_files:
        rows = json.loads(b_files[-1].read_text(encoding="utf-8")).get("output") or []
        out["drawing"] = {"hits": sum(1 for r in rows if r.get("hit")), "of": len(rows), "file": b_files[-1].name,
                          "rows": [{k: r.get(k) for k in ("id", "hit", "distance", "found", "check")} for r in rows]}
    return out


def score_f(results: Path, keys: dict) -> dict:
    out = {}
    for f in sorted(results.glob("F_*_*.json")):
        kid, system = f.stem.split("_")[1], "_".join(f.stem.split("_")[2:])
        key = keys.get(kid)
        d = json.loads(f.read_text(encoding="utf-8"))
        o = d.get("output") or {}
        exp = key["expected"]
        val, status = o.get("value"), o.get("status")
        ok_val = (exp["value"] is None and val is None) or (
            val is not None and exp["value"] is not None and abs(float(val) - float(exp["value"])) <= 0.01 * abs(float(exp["value"])))
        out.setdefault(system, []).append({"id": kid, "value": val, "status": status, "expected": exp,
                                           "correct": bool(ok_val and status == exp["status"])})
    return out


def main() -> int:
    keys = {}
    key_times = {}
    for kf in sorted((ROOT / "eval" / "keys").glob("*.json")):
        k = json.loads(kf.read_text(encoding="utf-8"))
        keys[k["id"]] = k
        key_times[k["id"]] = key_commit_time(kf)
    texts = load_page_texts()
    scores = {"first_runs": score_dir(ROOT / "eval" / "results", keys, texts, key_times)}
    rerun = ROOT / "eval" / "results" / "rerun"
    if rerun.exists():
        scores["rerun"] = score_dir(rerun, keys, texts, key_times)
    scores["F"] = score_f(ROOT / "eval" / "results", keys)
    (ROOT / "eval" / "results" / "scores.json").write_text(json.dumps(scores, indent=1, default=str), encoding="utf-8")

    for name in ("first_runs", "rerun"):
        if name not in scores:
            continue
        s = scores[name]
        bad = [k for k in s["key_before_run"] if not k["ok"]]
        print(f"\n## {name}: key-before-run {'OK for all ' + str(len(s['key_before_run'])) if not bad else 'FAILED: ' + str(bad)}")
        for system, sets in s["systems"].items():
            for set_name, m in sets.items():
                print(f"{system:9} {set_name}: recall(worst,mean) {m['page_recall_worst_mean']} | wrong(sum worst) "
                      f"{m['wrong_pages_sum']} {m['wrong_pages_worst']} | values {m['value_accuracy_worst_mean']} | "
                      f"evidence {m['evidence']} | verdict {m['verdict_matches'][0]}/{m['verdict_matches'][1]} | "
                      f"s median {m['seconds_median']} max {m['seconds_max']}")
        print("same-item:", s["same_item"], "| drawing:", s["drawing"] and f"{s['drawing']['hits']}/{s['drawing']['of']}",
              "| time:", s["time"])
        print(f"misses ({len(s['misses'])}):")
        for m in s["misses"]:
            print("  ", json.dumps(m, default=str))
    print("\nF:", json.dumps(scores["F"], default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
