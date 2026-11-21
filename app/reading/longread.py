"""Step 2: token count + Argon long read over the plant's pages.

The prompt starts with the plant's pages block, built from pages_all.json in n
order, so it is byte-identical on every run for the same plant and Gemini's
automatic cache is reused (ARCHITECTURE.md section 7). The task (with the RAW
change text, so this runs in parallel with Neon's understanding) comes after.
"""

from __future__ import annotations

from app.reading import schemas
from app.reading.settings import reading_settings

TASK = """

=== TASK ===
A proposed change to this plant (exactly as typed):
<<<{change}>>>

List every page above that is about the equipment this change concerns, INCLUDING pages that name it
differently (abbreviations such as "FLR WASH WTR", other wording on scope pages and data sheets), and the
P&ID and data-sheet pages of its system. Exclude look-alikes in other units or systems.
For each page give the file and page exactly as in its "=== file p.N ===" header, and one short reason.
"""

_token_cache: dict[str, int] = {}


def pages_block(pages_all: list[dict]) -> str:
    return "".join(f"=== {p['file']} p.{p['page']} ===\n{p['text']}\n" for p in pages_all)


def token_count(models, plant_id: str, block: str, store=None) -> dict:
    """{"value": N, "estimated": bool}. Counted once per plant: kept in memory and stored on
    the plant (the block does not change), so a new process or instance does not recount."""
    if plant_id in _token_cache:
        return {"value": _token_cache[plant_id], "estimated": False}
    if store is not None:
        known = (store.get_plant(plant_id) or {}).get("token_count") or {}
        if known.get("estimated") is False and known.get("value"):
            _token_cache[plant_id] = int(known["value"])
            return {"value": _token_cache[plant_id], "estimated": False}
    try:
        n = models.count_tokens(block)
        _token_cache[plant_id] = n
        if store is not None:
            store.mutate_plant(plant_id, lambda d: d.update(token_count={"value": n, "estimated": False}))
        return {"value": n, "estimated": False}
    except Exception:
        est = reading_settings()["long_read"]["chars_per_token_estimate"]
        return {"value": len(block) // est, "estimated": True}


def long_read(models, plant_id: str, pages_all: list[dict], change_text: str, store=None) -> dict:
    """-> {"status": "done" | "skipped: over limit" | "failed: <Error>", "pages": [...], "token_count": {...}}"""
    block = pages_block(pages_all)
    tokens = token_count(models, plant_id, block, store)
    limit = reading_settings()["long_read"]["token_limit"]
    if tokens["value"] > limit:
        return {"status": "skipped: over limit", "pages": [], "token_count": tokens,
                "message": f"this set is {tokens['value']} tokens, over the {limit:,} limit; "
                           "splitting is not available yet; code search only"}
    usage: dict = {}
    try:
        out = models.call("long_read", block + TASK.format(change=change_text), schemas.LONG_READ,
                          reading_settings()["thinking"]["long_read"], usage=usage)
    except Exception as e:
        return {"status": f"failed: {type(e).__name__}", "pages": [], "token_count": tokens, "usage": usage}
    known = {(p["file"], p["page"]) for p in pages_all}
    pages = [p for p in out.get("pages", []) if (p.get("file"), p.get("page")) in known]
    return {"status": "done", "pages": pages, "token_count": tokens, "usage": usage}
