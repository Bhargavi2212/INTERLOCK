"""Step 7b register clash check (no model). Firestore is the only source of truth.

A clash: a register entry for the same item (normalised item, or any shared
name) and the same attribute, whose approved value differs from the value
after this change. Because approved values are overlaid on the as-issued
inputs (scenario.py), an attribute the change does not touch keeps its
approved value and does not clash; one the change undoes does.
"""

from __future__ import annotations

from app.reading.evidence import norm
from app.rules.model import Disputed, Value


def _same_item(entry: dict, understanding: dict) -> bool:
    mine = {norm(understanding.get("item", ""))} | {norm(n) for n in understanding.get("names", [])}
    theirs = {norm(entry.get("item", ""))} | {norm(n) for n in entry.get("names", [])}
    mine.discard("")
    theirs.discard("")
    return bool(mine & theirs)


def _same_value(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return norm(a) == norm(b)


def find_clashes(register: list[dict], understanding: dict, after_values: dict) -> list[dict]:
    out = []
    for e in register:
        if not _same_item(e, understanding):
            continue
        proposed = after_values.get(e.get("attribute"))
        if isinstance(proposed, Disputed) or proposed is None:
            continue
        if isinstance(proposed, Value) and proposed.source == "register":
            continue  # untouched: still the approved value
        value = proposed.value if isinstance(proposed, Value) else proposed
        if not _same_value(e.get("value"), value):
            out.append({"entry_id": e.get("entry_id"), "attribute": e.get("attribute"),
                        "approved": e.get("value"), "proposed": value})
    return out
