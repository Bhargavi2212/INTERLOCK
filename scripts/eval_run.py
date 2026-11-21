"""Measurement runs (PHASE_4 Part 1, Amendments M7, M10; EVAL.md section 1). Bhargavi runs this:

    python scripts/eval_run.py --plant 27d049ccd64f --sets E,A,B --repeat-e 3 --stop-at 16:00

Gates (refuses to start): any eval/keys file modified or uncommitted; the plant's register
not empty (approved changes must never shape a measured run). Eval plant != demo plant.

Order (D4): Interlock E (x repeat), A, B; keyword E, A; one-call E (x repeat), A.
One change at a time, 5 s pause; a 429/5xx waits 10 s and retries once; a failure is
written as failed, never skipped. Stops cleanly at --stop-at (local time, HH:MM).
Every run writes eval/results/<set>_<id>_<system>_<run>.json with plant_id, started_at,
seconds and the full output. No scoring here (phase 5). Only the change text (E, A) or
item_query (B) from a key ever reaches a model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

PAUSE_S = 5
RETRY_WAIT_S = 10
RETRY_CODES = {429, 500, 502, 503, 504}


def keys_clean(root: Path = ROOT) -> bool:
    out = subprocess.run(["git", "status", "--porcelain", "eval/keys"], cwd=root, capture_output=True, text=True)
    return out.returncode == 0 and out.stdout.strip() == ""


def preflight(store, plant_id: str, root: Path = ROOT) -> str | None:
    """The reason the runner must refuse, or None."""
    if not keys_clean(root):
        return "eval/keys has modified or uncommitted files (keys must be committed before any run)"
    plant = store.get_plant(plant_id)
    if not plant or plant.get("ingest_status") != "done":
        return f"plant {plant_id} not found or not ingested"
    if store.list_register(plant_id):
        return f"plant {plant_id} has approved changes in its register (eval plant must have none)"
    return None


def result_path(root: Path, set_name: str, key_id: str, system: str, run: int) -> Path:
    return root / "eval" / "results" / f"{set_name}_{key_id}_{system}_{run}.json"


def load_keys(set_name: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "eval" / "keys").glob(f"{set_name}*.json"))]


def _code(e: Exception) -> int | None:
    for attr in ("code", "status_code", "status"):
        v = getattr(e, attr, None)
        if isinstance(v, int):
            return v
    return None


def run_one(fn):
    """(output, error_class, seconds); one extra retry after 10 s on 429/5xx."""
    start = time.monotonic()
    for attempt in (1, 2):
        try:
            return fn(), None, round(time.monotonic() - start, 1)
        except Exception as e:  # recorded by class name, never the message
            if attempt == 1 and _code(e) in RETRY_CODES:
                time.sleep(RETRY_WAIT_S)
                continue
            return None, type(e).__name__, round(time.monotonic() - start, 1)


def write(path: Path, plant_id: str, started: str, seconds: float, output, error) -> None:
    path.write_text(json.dumps({"plant_id": plant_id, "started_at": started, "seconds": seconds,
                                "state": "failed" if error else "done", "error": error, "output": output},
                               indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from app.explain.carbon import explain
    from app.explain.headlines import headlines
    from app.reading.models import get_models
    from app.reading.pipeline import check_change
    from app.reading.understand import understand
    from app.store.base import get_store
    from eval.baselines.keyword import keyword_pages
    from eval.baselines.one_call import one_call

    ap = argparse.ArgumentParser()
    ap.add_argument("--plant", required=True)
    ap.add_argument("--sets", default="E,A,B")
    ap.add_argument("--repeat-e", type=int, default=3)
    ap.add_argument("--systems", default="interlock,keyword,one_call")
    ap.add_argument("--stop-at", default="16:00")
    args = ap.parse_args()

    store, models = get_store(), get_models()
    reason = preflight(store, args.plant)
    if reason:
        print(f"REFUSED: {reason}")
        return 2
    plant = store.get_plant(args.plant)

    stop = datetime.now().replace(hour=int(args.stop_at[:2]), minute=int(args.stop_at[3:]), second=0)
    sets = [s.strip().upper() for s in args.sets.split(",")]
    systems = [s.strip() for s in args.systems.split(",")]
    pages_all = store.get_pages_all(args.plant)
    print(f"eval on plant {args.plant} ({plant['page_count']} pages); keys clean; register empty; stop at {args.stop_at}")

    def runs(set_name, system):
        if set_name == "E" and system in ("interlock", "one_call"):
            return args.repeat_e
        return 1

    jobs = []
    for system in [s for s in ("interlock", "keyword", "one_call") if s in systems]:
        for set_name in [s for s in ("E", "A", "B") if s in sets]:
            if set_name == "B" and system != "interlock":
                continue
            for run in range(1, runs(set_name, system) + 1):
                jobs.append((system, set_name, run))

    for system, set_name, run in jobs:
        if set_name == "B":
            if datetime.now() >= stop:
                print("stop time reached")
                return 0
            from score_b import score_b_rows
            started = datetime.now().isoformat(timespec="seconds")
            out, err, secs = run_one(lambda: score_b_rows(store, models, args.plant))
            path = result_path(ROOT, "B", "all", system, run)
            write(path, args.plant, started, secs, out, err)
            print(f"B all {system} run {run}: {'failed ' + err if err else 'done'} {secs}s -> {path.name}")
            time.sleep(PAUSE_S)
            continue
        for key in load_keys(set_name):
            if datetime.now() >= stop:
                print("stop time reached")
                return 0
            text = key["change"]                           # the only key field a model sees
            started = datetime.now().isoformat(timespec="seconds")
            if system == "interlock":
                cid = f"eval-{key['id']}-{run}-{int(time.time())}"
                fn = lambda: check_change(  # noqa: E731
                    store, models, args.plant, cid, text,
                    explain_fn=lambda dis, values: explain(models, text, dis, values),
                    headlines_fn=lambda after, dis, clashes: headlines(models, after, dis, clashes))
            elif system == "keyword":
                def fn():
                    u = understand(models, text)
                    return {"item": u.get("item"), "pages": keyword_pages(pages_all, u.get("item", ""))}
            else:
                def fn():
                    usage: dict = {}
                    out = one_call(models, pages_all, text, usage)
                    return {**out, "usage": usage}
            out, err, secs = run_one(fn)
            path = result_path(ROOT, set_name, key["id"], system, run)
            write(path, args.plant, started, secs, out, err)
            print(f"{key['id']} {system} run {run}: {'failed ' + err if err else 'done'} {secs}s -> {path.name}",
                  flush=True)
            time.sleep(PAUSE_S)
    print("all runs done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
