"""Set F: the rule engine's math vs one Gemini call doing the math (PHASE_5 spec section 2 + G2).

    python scripts/run_f.py --systems interlock           # code only, no key, no network
    python scripts/run_f.py --systems interlock,one_call  # one_call needs MODEL_ARGON and the key (Bhargavi runs it)

Both systems get the same inputs: the F key's inputs (value, unit, file, page, quote). Writes
eval/results/F_<id>_<system>.json; score_eval.py scores them (within 1% and status equal).

Interlock: Values from the key (source document, evidence_ok true); the key's velocity_band
becomes a DocLimit whose applies_to comes from the key (or the quote's role words), never the
3.0 m/s default silently. R3 held with the inflow missing: the scored value is the pump-out
time the engine reports in its notes.
One call: one Argon call (thinking low, structured output) given the input pages' text from
the local PDFs in data/bhel, the calculation sentence, the rule's formula and its limits from
rules.yaml, and the same inputs; "compute it".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rules.checks import FORMULAS  # noqa: E402
from app.rules.engine import load_rules, run_rule  # noqa: E402
from app.rules.model import DocLimit, Value  # noqa: E402
from app.rules.units import matches_phrase  # noqa: E402

RULE_OF = {"F1": "R1", "F2": "R3", "F3": "R2"}
F_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "number"}, "unit": {"type": "string"},
                   "status": {"type": "string", "enum": ["OK", "flagged", "held"]},
                   "working": {"type": "string"}},
    "required": ["value", "unit", "status", "working"],
}


def rule_of(key: dict) -> str:
    m = re.match(r"\s*(R\d)\b", key.get("calculation", ""))
    return m.group(1) if m else RULE_OF[key["id"]]


def band_limit(inp: dict, rule_id: str, line_nb) -> DocLimit:
    """G2: the key's velocity_band as a DocLimit; applies_to from the key, else the quote's role words."""
    lo, hi = (float(x) for x in str(inp["value"]).replace("–", "-").split("-"))
    roles = load_rules()["rules"]["R1"]["line_roles"]
    applies_to = inp.get("applies_to") or matches_phrase(inp.get("quote", ""), roles) or ""
    nb = int(line_nb) if line_nb is not None else None
    return DocLimit(rule_id=rule_id, name="velocity band", low=lo, high=hi, unit=inp["unit"],
                    applies_from_nb=nb, applies_to_nb=nb, file=inp["file"], page=int(inp["page"]),
                    quote=inp["quote"], applies_to=applies_to)


def interlock(key: dict) -> dict:
    rule_id = rule_of(key)
    values, limits = {}, []
    line_nb = next((i["value"] for i in key["inputs"] if i["name"] == "line_nb"), None)
    for inp in key["inputs"]:
        if inp["name"] == "velocity_band":
            limits.append(band_limit(inp, rule_id, line_nb))
            continue
        values[inp["name"]] = Value(value=inp["value"], unit=inp["unit"], file=inp["file"],
                                    page=int(inp["page"]), quote=inp["quote"], evidence_ok=True, source="document")
    r = run_rule(rule_id, values, limits)
    value = r.value
    if r.status == "held" and value is None:
        m = next((re.search(r"pump-out only ([\d.]+) min", n) for n in (r.notes or []) if "pump-out" in n), None)
        value = float(m.group(1)) if m else None
    return {"rule_id": rule_id, "value": value, "unit": r.unit or ("min" if value is not None else ""),
            "status": r.status, "limit": r.limit, "limit_source": r.limit_source, "message": r.message,
            "notes": list(r.notes or []), "assumptions": list(r.assumptions or []),
            "doc_limits": [{"applies_to": d.applies_to, "low": d.low, "high": d.high} for d in limits]}


def page_text(file: str, page: int) -> str:
    import pymupdf
    with pymupdf.open(ROOT / "data" / "bhel" / Path(file).name) as doc:
        return doc[page - 1].get_text()


def one_call_prompt(key: dict) -> str:
    rule_id = rule_of(key)
    pages = sorted({(Path(i["file"]).name, int(i["page"])) for i in key["inputs"]})
    texts = "\n\n".join(f"=== {f} page {p} ===\n{page_text(f, p)}" for f, p in pages)
    limits = json.dumps(load_rules()["rules"][rule_id], default=str)
    inputs = json.dumps(key["inputs"])
    return (f"Compute this engineering check by hand and report the result.\n\nCheck: {key['calculation']}\n"
            f"Formula: {FORMULAS[rule_id]}\nRule settings and limits: {limits}\n"
            f"Inputs (each with its page and quote): {inputs}\n\nPages:\n{texts}\n\n"
            "Return value (the computed result number), unit, status (OK if within the limit, flagged if not, "
            "held if a required input is missing; when held, value is the part you can compute), and working.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default="interlock")
    ap.add_argument("--plant", default="", help="unused; kept for the spec's command line")
    args = ap.parse_args()
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    models = None
    if "one_call" in systems:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        from app.reading.models import Models
        models = Models()
    for kf in sorted((ROOT / "eval" / "keys").glob("F*.json")):
        key = json.loads(kf.read_text(encoding="utf-8"))
        for system in systems:
            started, t0 = datetime.now().isoformat(timespec="seconds"), time.monotonic()
            try:
                if system == "interlock":
                    out = interlock(key)
                else:
                    usage = {}
                    out = models.call("one_call", one_call_prompt(key), F_SCHEMA, "low", usage=usage)
                    out["usage"] = usage
                state, err = "done", None
            except Exception as e:  # noqa: BLE001  (recorded, never hidden)
                out, state, err = None, "failed", f"{type(e).__name__}: {e}"
            rec = {"id": key["id"], "system": system, "started_at": started,
                   "seconds": round(time.monotonic() - t0, 1), "state": state, "error": err, "output": out}
            path = ROOT / "eval" / "results" / f"F_{key['id']}_{system}.json"
            path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
            o = out or {}
            print(f"{key['id']} {system}: {state} value {o.get('value')} {o.get('unit')} status {o.get('status')}"
                  f" (expected {key['expected']['value']} {key['expected']['status']}) {err or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
