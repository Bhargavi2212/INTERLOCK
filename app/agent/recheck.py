"""Server re-check of a proposed fix (no model). The agent never decides.

Rebuilds the change's scenario from its stored result (checked values and drawing readings,
shared-discharge values, checked limits, the understanding's changes, the plant's drawing
pages) with the CURRENT register (same item and unit tag), overlays the fix values
(source "fix"), runs the live rules, states the drawing assumption, checks the register
for clashes, and decides `proven` against the change's own results_after (RULES.md, Proven).
PHASE_4 Amendment M4: it rebuilds; it never reuses objects from the change check.
"""

from __future__ import annotations

from app.agent.levers import allowed, base_installed
from app.reading.scenario import add_drawing_assumption, build_scenario, doc_limits, fix_values_from
from app.register.clash import find_clashes
from app.rules import run_rules
from app.rules.model import result_from_dict
from app.verdict import proven


def rebuild(store, change: dict, fix: list[dict] | None = None) -> dict:
    """-> {sc, results} for the change, with a fix overlaid if given."""
    plant_id = change["plant_id"]
    pages_all = store.get_pages_all(plant_id)
    drawing_pages = {(p["file"], p["page"]) for p in pages_all if p.get("is_drawing")}
    register = store.list_register(plant_id)
    u = change["understanding"]
    shared = change.get("shared_discharge") or []
    sc = build_scenario(change.get("values") or [], shared, u.get("changes", []), change["text"], register,
                        drawing_pages, u, fix_values=fix_values_from(fix) if fix else None)
    results = run_rules(sc["after"], doc_limits(change.get("limits") or []))
    add_drawing_assumption(results, [s for s in shared if s.get("source") == "drawing"], sc)
    return {"sc": sc, "results": results, "register": register, "understanding": u}


def recheck(store, change: dict, fix: list[dict]) -> dict:
    """-> {proven, reasons, results_fixed, clashes, levers_ok}."""
    ok, why = allowed(fix, base_installed(change, store.list_register(change["plant_id"])))
    if not ok:
        return {"proven": False, "reasons": [why], "results_fixed": [], "clashes": [], "levers_ok": False}
    built = rebuild(store, change, fix)
    clashes = find_clashes(built["register"], built["understanding"], built["sc"]["after_values"])
    before = [result_from_dict(r) for r in change.get("results_after", [])]
    verdict_of_fix = proven(before, built["results"], clashes)
    return {"proven": verdict_of_fix["proven"], "reasons": verdict_of_fix["reasons"],
            "results_fixed": [r.to_dict() for r in built["results"]], "clashes": clashes, "levers_ok": True}
