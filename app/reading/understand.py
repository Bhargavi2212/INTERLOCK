"""Step 1: understand the change (Neon), structured output."""

from __future__ import annotations

from app.reading import schemas
from app.reading.settings import reading_settings
from app.rules.engine import INPUT_QUANTITY

PROMPT = """You read a proposed change to a process plant and describe it for a document search.

Change (exactly as the engineer typed it):
<<<{change}>>>

Return:
- item: the equipment the change is about, as written in plant documents (e.g. "SG Unit-1 floor wash water transfer pumps").
- names: every name or abbreviation plant documents may use for this exact item: full name, short name,
  abbreviations (e.g. "FLR WASH WTR", "FWW"), singular and plural, with and without the unit tag. 5-15 names.
- system: the system or area it belongs to (e.g. "SG Unit-1 floor wash").
- unit_tag: the unit / train identifier that separates it from look-alikes (e.g. "Unit-1"), or "" if none.
- is_pump_item: true if the item is a pump set.
- changes: each quantity the change alters, using ONLY these input names: {inputs}. Never standby_required:
  "no spare" or "no standby" is said through installed and working (e.g. installed 1).
  "from" = the value before (as stated in the change, or "" if not stated), "to" = the value after, "unit" = its unit
  ("count" for numbers of pumps, "" for an arrangement such as "2W+1S"). Never compute or convert.
"""


def understand(models, change_text: str) -> dict:
    inputs = ", ".join(n for n in sorted(INPUT_QUANTITY) if n != "standby_required")
    out = models.call("understand", PROMPT.format(change=change_text, inputs=inputs),
                      schemas.UNDERSTAND, reading_settings()["thinking"]["understand"])
    names = [n for n in out.get("names", []) if str(n).strip()]
    for extra in (out.get("item"), out.get("system")):
        if extra and extra not in names:
            names.append(extra)
    out["names"] = names
    out["changes"] = [c for c in out.get("changes", [])
                      if c.get("input") in INPUT_QUANTITY and c.get("input") != "standby_required"]
    return out
