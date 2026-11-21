"""Validate a proposed fix against levers.yaml (no model)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.register.clash import same_item
from app.rules.engine import load_rules
from app.rules.units import UnknownUnit, to_base

OUTSIDE = "agent proposed a change outside the allowed levers"


@lru_cache(maxsize=1)
def levers() -> dict:
    with open(Path(__file__).with_name("levers.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def base_installed(change: dict, register: list[dict]) -> float | None:
    """Installed pumps the fix adds to: the approved register value for this item and unit, else the
    documents' value if they agree; None if disputed or absent (then there is no installed lever)."""
    u = change.get("understanding", {})
    approved = [e for e in register if e.get("attribute") == "installed" and same_item(e, u)]
    if approved:
        return float(sorted(approved, key=lambda e: e.get("approved_at", ""))[-1]["value"])
    cfg = load_rules()["units"]
    seen = set()
    for v in change.get("values", []):
        if v.get("input") == "installed" and v.get("evidence_ok"):
            try:
                seen.add(to_base("count", v["value"], v.get("unit") or "count", cfg)[0])
            except UnknownUnit:
                return None
    return seen.pop() if len(seen) == 1 else None


def allowed(fix: list[dict], base: float | None) -> tuple[bool, str]:
    lv = levers()
    if not fix:
        return False, "the fix changes nothing"
    for f in fix:
        name, to = f.get("input"), f.get("to")
        if name == "line_nb":
            try:
                ok = float(to) in [float(s) for s in lv["line_nb"]["sizes"]]
            except (TypeError, ValueError):
                ok = False
            if not ok:
                return False, f"{OUTSIDE}: line_nb {to} is not a standard size {lv['line_nb']['sizes']}"
        elif name == "installed":
            if base is None:
                return False, f"{OUTSIDE}: installed pumps are disputed or unknown, so no pumps can be added"
            try:
                ok = float(to) - base in [float(a) for a in lv["installed"]["add"]]
            except (TypeError, ValueError):
                ok = False
            if not ok:
                return False, f"{OUTSIDE}: installed {to} is not {base:g} + {lv['installed']['add']}"
        else:
            return False, f"{OUTSIDE}: {name}"
    return True, ""
