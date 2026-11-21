"""Approve -> register entries (no model). Firestore is the only source of truth.

Approval needs: the latest fix for the change proven by the server, proven AGAIN now (the
register may have changed), and the engineer's tick for every document disagreement listed
(PHASE_4 Amendment M6). One entry per changed attribute: the change's own values and the fix's.
Entries carry the item, names and unit tag (M5) so overlay and clash match item AND unit.
"""

from __future__ import annotations

from app.agent.recheck import recheck
from app.store.base import new_id, now


class NotApproved(Exception):
    """409: the reason is safe to show."""


def disagreement_text(d: dict) -> str:
    return f"{d['attribute']} (" + "; ".join(f"{x['file']} p.{x['page']} = {x['value']}" for x in d["values"]) + ")"


def approve(store, change: dict, resolved: list[str]) -> list[dict]:
    fix = (change.get("fix") or {})
    if not (fix.get("recheck") or {}).get("proven"):
        raise NotApproved("no proven fix for this change")
    again = recheck(store, change, fix.get("fix") or [])
    if not again["proven"]:
        raise NotApproved("the fix is no longer proven: " + "; ".join(again["reasons"]))
    open_ = [d for d in change.get("disagreements") or [] if d["attribute"] not in set(resolved or [])]
    if open_:
        raise NotApproved("documents disagree; resolve before approving: "
                          + ", ".join(disagreement_text(d) for d in open_))

    u = change["understanding"]
    ticked = [disagreement_text(d) for d in change.get("disagreements") or []]
    stamp = now()
    base = {"item": u.get("item"), "names": u.get("names", []), "system": u.get("system"),
            "unit_tag": u.get("unit_tag", ""), "approved_at": stamp, "change_id": change["change_id"],
            "resolved_disagreements": ticked}
    entries = [{**base, "entry_id": new_id(), "attribute": c["input"], "value": c["to"],
                "unit": c.get("unit", ""), "fix": False} for c in u.get("changes", [])]
    entries += [{**base, "entry_id": new_id(), "attribute": f["input"], "value": f["to"],
                 "unit": f.get("unit", ""), "fix": True} for f in fix.get("fix") or []]
    store.add_register_entries(change["plant_id"], entries)
    return entries
