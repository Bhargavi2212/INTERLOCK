"""Collect the live demo outcomes (PHASE_5 spec section 3 + amendments 6-8) from Firestore with ADC.

    python scripts/collect_demo.py --project interlock-515416 --plant 9eeb30bca0d5

No access code, no Gemini key, no .env: Application Default Credentials only.
Writes eval/results/demo_<plant>.json: every fix job (outcome, proven, reasons, environment),
the register entries, and each change those touch (text, verdict, register clashes).
Fix jobs are read because a later "Find a fix" overwrites the fix stored on the change (amendment 7).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--plant", required=True)
    ap.add_argument("--database", default="(default)")
    args = ap.parse_args()
    from google.cloud import firestore
    db = firestore.Client(project=args.project, database=args.database)
    plant = db.collection("plants").document(args.plant)

    jobs = [d.to_dict() for d in db.collection("jobs").where("plant_id", "==", args.plant).stream()]
    fix_jobs = sorted((j for j in jobs if j.get("type") == "fix"), key=lambda j: str(j.get("created_at")))
    register = [d.to_dict() | {"entry_id": d.id} for d in plant.collection("register").stream()]

    change_ids = {j.get("change_id") for j in fix_jobs} | {e.get("change_id") for e in register}
    change_ids |= {j.get("change_id") for j in jobs if j.get("type") == "change"}
    changes = {}
    for cid in sorted(c for c in change_ids if c):
        snap = plant.collection("changes").document(cid).get()
        if not snap.exists:
            continue
        c = snap.to_dict()
        verdict = c.get("verdict") or (c.get("result") or {}).get("verdict")
        fix = c.get("fix") or {}
        changes[cid] = {"text": c.get("text") or c.get("change_text"), "state": c.get("state"),
                        "verdict": verdict, "clashes": c.get("clashes") or (c.get("result") or {}).get("clashes"),
                        "fix_outcome": fix.get("outcome"),
                        "fix_proven": (fix.get("recheck") or {}).get("proven")}

    out = {"plant": args.plant,
           "fix_jobs": [{k: j.get(k) for k in ("job_id", "change_id", "state", "created_at", "updated_at", "result", "error")}
                        for j in fix_jobs],
           "register": register, "changes": changes}
    path = ROOT / "eval" / "results" / f"demo_{args.plant}.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"fix jobs {len(fix_jobs)}, register entries {len(register)}, changes {len(changes)} -> {path.name}")
    for j in out["fix_jobs"]:
        print(" fix", j["change_id"], j["state"], json.dumps(j["result"], default=str)[:200])
    for cid, c in changes.items():
        print(" change", cid, c["verdict"] if not isinstance(c["verdict"], dict) else c["verdict"].get("verdict"),
              "|", (c["text"] or "")[:80], "| clashes", bool(c["clashes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
