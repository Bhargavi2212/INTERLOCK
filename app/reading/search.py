"""Step 2 code search (no model): every page, case-insensitive, spaces and hyphens ignored."""

from __future__ import annotations

import re


def squash(text: str) -> str:
    return re.sub(r"[\s\-_]+", "", str(text or "")).lower()


def search_pages(pages_all: list[dict], names: list[str], unit_tag: str | None = None) -> list[dict]:
    """Pages containing any name. A hit without the unit tag on the page is kept as
    an 'other-unit look-alike' candidate; the same-item check decides."""
    terms = [(n, squash(n)) for n in dict.fromkeys(names) if squash(n)]
    tag = squash(unit_tag) if unit_tag else ""
    out = []
    for p in pages_all:
        s = squash(p["text"])
        hits = [n for n, t in terms if t in s]
        if hits:
            out.append({"file": p["file"], "page": p["page"], "n": p["n"], "found_by": "search",
                        "names": hits, "look_alike": bool(tag) and tag not in s})
    return out


def merge_candidates(search_hits: list[dict], long_read: list[dict]) -> list[dict]:
    """Union by {file, page}; found_by = search | longread | both."""
    out: dict[tuple, dict] = {}
    for h in search_hits:
        out[(h["file"], h["page"])] = dict(h)
    for p in long_read:
        key = (p["file"], p["page"])
        if key in out:
            out[key]["found_by"] = "both"
            out[key]["why"] = p.get("why", "")
        else:
            out[key] = {"file": p["file"], "page": p["page"], "found_by": "longread",
                        "why": p.get("why", ""), "names": [], "look_alike": False}
    return list(out.values())
