"""Score set B (P&ID locate). Bhargavi runs this (needs the key), only after calibration:

    python scripts/score_b.py --plant <plant_id>

For each eval/keys/B*.json: the understanding is built from item_query ONLY (never
item, notes or any other key field); the drawing step runs alone on the key's page
(matched by file name, without folder); the model's label_box centre is compared with
the key box centre (EVAL.md section 4): hit if within 0.03 of the page; a found:false
key is a hit if the item is not found. Raw output: eval/results/b_<time>.json.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.drawing.boxes import distance  # noqa: E402
from app.drawing.vision import look_on_page  # noqa: E402
from app.reading.models import get_models  # noqa: E402
from app.reading.understand import understand  # noqa: E402
from app.store.base import get_store  # noqa: E402

HIT = 0.03


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plant", required=True)
    args = ap.parse_args()
    store, models = get_store(), get_models()
    pages = store.get_pages_all(args.plant)
    rows, hits = [], 0
    for path in sorted((ROOT / "eval" / "keys").glob("B*.json")):
        key = json.loads(path.read_text(encoding="utf-8"))
        query = key["item_query"]                                  # the only field the scorer uses as input
        p = next((x for x in pages if Path(x["file"]).name == key["file"] and x["page"] == key["page"]), None)
        if p is None:
            print(f"{key['id']}: page {key['file']} p.{key['page']} not in plant")
            return 1
        u = understand(models, query)
        res = look_on_page(models, u, store.get_page(args.plant, p["n"]), store.get_page_png(args.plant, p["n"]))
        res.pop("_crop", None)
        if key.get("found", True):
            dist = distance(res["label_box"], key["box"]) if res["found"] and res["label_box"] else None
            hit = dist is not None and dist <= HIT
        else:
            dist, hit = None, not res["found"]
        hits += hit
        rows.append({"id": key["id"], "query": query, "hit": hit, "distance": dist, "found": res["found"],
                     "check": res["check"], "label_box": res["label_box"], "key_box": key.get("box"),
                     "anchor": res["anchor_text"], "why": res["why"]})
        print(f"{key['id']} {'hit ' if hit else 'MISS'} dist={None if dist is None else round(dist, 4)} "
              f"found={res['found']} ({res['check']})")
    out = ROOT / "eval" / "results" / f"b_{time.strftime('%H%M%S')}.json"
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{hits}/{len(rows)} hits; raw: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
