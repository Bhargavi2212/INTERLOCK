"""Steps 1-9 for one change (ARCHITECTURE.md section 1; drawing is phase 3).

understand (Neon) || long read on the raw change text (Argon), in parallel
-> code search -> same item (Decisions) -> values (Argon) -> evidence (code)
-> scenario + rules R1-R3 (code) -> register clash (code)
-> explain (Carbon) || headlines (Hydrogen), in parallel -> verdict (code).
Seconds per step are recorded in steps[]. Models are reached only via models.py.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from app.reading.evidence import check_limit, check_value, page_texts, quote_on_page
from app.reading.longread import long_read
from app.reading.sameitem import same_item
from app.reading.scenario import build_scenario, doc_limits
from app.reading.search import merge_candidates, search_pages
from app.reading.understand import understand
from app.reading.values import pull_values
from app.register.clash import find_clashes
from app.rules import run_rules
from app.verdict import verdict

STEP_NAMES = ["understand", "long_read", "search", "same_item", "values", "evidence", "rules",
              "clash", "explain", "headlines", "verdict"]


class Steps:
    def __init__(self, progress=None):
        self.items: list[dict] = []
        self.progress = progress or (lambda steps, name: None)

    def run(self, name: str, fn):
        self.progress(self.items, name)
        start = time.monotonic()
        try:
            out = fn()
            self.items.append({"name": name, "state": "done", "seconds": round(time.monotonic() - start, 1)})
            return out
        except Exception as e:
            self.items.append({"name": name, "state": f"failed: {type(e).__name__}",
                               "seconds": round(time.monotonic() - start, 1)})
            raise


def _timed(fn):
    start = time.monotonic()
    try:
        return fn(), None, round(time.monotonic() - start, 1)
    except Exception as e:
        return None, e, round(time.monotonic() - start, 1)


def check_shared(shared: list[dict], texts: dict) -> list[dict]:
    out = []
    for s in shared:
        text = texts.get((s.get("file"), int(s.get("page") or 0)))
        ok, why = quote_on_page(s.get("quote", ""), text) if text is not None else (False, "page not in this plant")
        out.append({**s, "evidence_ok": ok, "evidence_reason": why if not ok else "ok"})
    return out


def check_change(store, models, plant_id: str, change_id: str, text: str, progress=None,
                 explain_fn=None, headlines_fn=None) -> dict:
    t0 = time.monotonic()
    steps = Steps(progress)
    plant = store.get_plant(plant_id)
    pages_all = store.get_pages_all(plant_id)
    texts = page_texts(pages_all)

    # 1 || 2: understanding and the long read (raw change text) in parallel
    steps.progress(steps.items, "understand + long_read")
    with ThreadPoolExecutor(max_workers=2) as ex:
        fu = ex.submit(_timed, lambda: understand(models, text))
        fl = ex.submit(_timed, lambda: long_read(models, plant_id, pages_all, text, store))
        (u, u_err, u_s), (lr, lr_err, lr_s) = fu.result(), fl.result()
    steps.items.append({"name": "understand", "state": "done" if not u_err else f"failed: {type(u_err).__name__}",
                        "seconds": u_s})
    if lr_err:
        lr = {"status": f"failed: {type(lr_err).__name__}", "pages": [], "token_count": None}
    steps.items.append({"name": "long_read", "state": lr["status"], "seconds": lr_s})
    if u_err:
        raise u_err  # without the understanding nothing else can run

    hits = steps.run("search", lambda: search_pages(pages_all, u["names"], u.get("unit_tag")))
    cands = merge_candidates(hits, lr["pages"])
    judged, mode, mode_note = steps.run("same_item", lambda: same_item(models, cands, texts, u))
    kept = [c for c in judged if c["kept"]]

    try:
        raw = steps.run("values", lambda: pull_values(models, u, kept, pages_all))
    except Exception:
        raw = {"values": [], "limits": [], "shared_discharge": [], "design_basis_pages": []}

    def evidence():
        return ([check_value(v, texts) for v in raw.get("values", [])],
                [check_limit(lim, texts) for lim in raw.get("limits", [])],
                check_shared(raw.get("shared_discharge", []), texts))
    values, limits, shared = steps.run("evidence", evidence)

    register = store.list_register(plant_id)

    def rules():
        sc = build_scenario(values, shared, u["changes"], text, register)
        lims = doc_limits(limits)
        return sc, run_rules(sc["issued"], lims), run_rules(sc["after"], lims)
    sc, issued, after = steps.run("rules", rules)
    clashes = steps.run("clash", lambda: find_clashes(register, u, sc["after_values"]))

    # explain || headlines (C6 wires the model calls; absent -> nothing / rule messages)
    explanations, headlines = [], [r.message for r in after if r.status != "OK"]
    if explain_fn or headlines_fn:
        with ThreadPoolExecutor(max_workers=2) as ex:
            fe = ex.submit(_timed, lambda: explain_fn(sc["disagreements"], values) if explain_fn and sc["disagreements"] else [])
            fh = ex.submit(_timed, lambda: headlines_fn(after, sc["disagreements"], clashes) if headlines_fn else headlines)
            (ex_out, ex_err, ex_s), (hl_out, hl_err, hl_s) = fe.result(), fh.result()
        explanations = ex_out if not ex_err else [{"note": "explanation unavailable"}]
        headlines = hl_out if not hl_err else headlines
        steps.items.append({"name": "explain", "state": "done" if not ex_err else "failed", "seconds": ex_s})
        steps.items.append({"name": "headlines", "state": "done" if not hl_err else "failed", "seconds": hl_s})

    v = steps.run("verdict", lambda: verdict(after, sc["disagreements"], clashes, plant["page_count"]))

    return {
        "change_id": change_id, "plant_id": plant_id, "text": text, "understanding": u,
        "seconds_total": round(time.monotonic() - t0, 1), "steps": steps.items,
        "page_count": plant["page_count"],
        "token_count": lr.get("token_count"), "long_read": lr["status"], "long_read_message": lr.get("message"),
        "long_read_usage": lr.get("usage"),
        "same_item_mode": mode, "same_item_note": mode_note,
        "pages": [{k: c.get(k) for k in ("file", "page", "found_by", "same_item_p", "uncertain", "why", "look_alike")}
                  for c in kept] + [
            {"file": f, "page": p, "found_by": "design basis", "same_item_p": None, "uncertain": False,
             "why": "design-basis limit used (evidence checked)", "look_alike": False}
            for f, p in sorted({(lim["file"], int(lim["page"])) for lim in limits if lim.get("evidence_ok")})
            if (f, p) not in {(c["file"], c["page"]) for c in kept}],
        "pages_rejected": [{"file": c["file"], "page": c["page"], "same_item_p": c.get("same_item_p")}
                           for c in judged if not c["kept"]],
        "design_basis_pages": raw.get("design_basis_pages", []),
        "values": values, "limits": limits, "shared_discharge": shared,
        "disagreements": sc["disagreements"], "explanations": explanations,
        "results_issued": [r.to_dict() for r in issued], "results_after": [r.to_dict() for r in after],
        "clashes": clashes, "verdict": v, "headlines": headlines,
    }
