"""Run one change through steps 1-9 on a plant from the live upload. Bhargavi runs this.

    gcloud auth application-default login      (once; reads Firestore / GCS as you)
    python scripts/run_change.py --plant <plant_id> "<change text>"

Needs .env (GEMINI_API_KEY, MODEL_*, GCP_PROJECT, GCS_BUCKET). Stores the
result like the live service does, prints a summary with seconds per step, and
writes the raw result to eval/results/run_<change_id>.json. Never prints the key.
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.reading.models import get_models  # noqa: E402
from app.reading.pipeline import check_change  # noqa: E402
from app.store.base import get_store, new_id  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plant", required=True)
    ap.add_argument("change")
    args = ap.parse_args()

    store = get_store()
    plant = store.get_plant(args.plant)
    if not plant or plant.get("ingest_status") != "done":
        print(f"plant {args.plant} not found or not ingested")
        return 1
    change_id = new_id()
    print(f"plant {plant['name']} ({plant['page_count']} pages); change {change_id}")
    res = check_change(store, get_models(), args.plant, change_id, args.change,
                       progress=lambda steps, name: print(f"  ... {name}", flush=True))
    store.put_change(args.plant, change_id, res)

    print(f"\nVERDICT: {res['verdict']['label']}   ({res['seconds_total']} s total)")
    print("steps:", ", ".join(f"{s['name']} {s['seconds']}s{'' if s['state'] == 'done' else ' [' + s['state'] + ']'}"
                              for s in res["steps"]))
    print(f"long read usage (input / cached / output / thought tokens): {res.get('long_read_usage')}")
    print(f"long read: {res['long_read']}; tokens {res['token_count']}; same-item: {res['same_item_mode']} "
          f"{res['same_item_note']}")
    print(f"\nPAGES kept ({len(res['pages'])}):")
    for p in res["pages"]:
        print(f"  {p['file']} p.{p['page']}  found_by={p['found_by']}  p={p['same_item_p']}  "
              f"{'UNCERTAIN ' if p['uncertain'] else ''}{(p.get('why') or '')[:80]}")
    print(f"  rejected: {[(p['file'], p['page'], p['same_item_p']) for p in res['pages_rejected']]}")
    print(f"\nVALUES ({len(res['values'])}):")
    for v in res["values"]:
        mark = "ok " if v["evidence_ok"] else "XX "
        print(f"  {mark}{v['input']} = {v['value']} {v['unit']}  ({v['file']} p.{v['page']}) "
              f"\"{v['quote'][:70]}\"{'' if v['evidence_ok'] else '  <- ' + v['evidence_reason']}")
    for lim in res["limits"]:
        print(f"  {'ok ' if lim['evidence_ok'] else 'XX '}limit {lim.get('applies_to')} {lim.get('low')}-{lim.get('high')} "
              f"{lim.get('unit')} NB {lim.get('applies_from_nb')}-{lim.get('applies_to_nb')} ({lim['file']} p.{lim['page']})")
    for s in res["shared_discharge"]:
        print(f"  {'ok ' if s['evidence_ok'] else 'XX '}shared_discharge = {s['value']} ({s['file']} p.{s['page']})")
    print("\nDISAGREEMENTS:", json.dumps(res["disagreements"]))
    for label, key in (("AS ISSUED", "results_issued"), ("AFTER CHANGE", "results_after")):
        print(f"\n{label}:")
        for r in res[key]:
            print(f"  {r['rule_id']} {r['status']}: {r['message'][:160]}")
            for n in r["notes"]:
                print(f"      note: {n}")
    print("\nCLASHES:", res["clashes"])

    out = ROOT / "eval" / "results" / f"run_{change_id}.json"
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nraw result: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
