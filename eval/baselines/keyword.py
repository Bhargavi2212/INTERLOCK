"""Keyword baseline (EVAL.md section 3, PHASE_4 Amendment M7).

Pages containing the change's item string exactly (spaces, hyphens and case ignored).
A free-text change has no item field, so the item string is Neon's `item` as returned.
No other names, no long read, no same-item check: it measures what those add.
"""

from __future__ import annotations

from app.reading.search import squash


def keyword_pages(pages_all: list[dict], item: str) -> list[dict]:
    target = squash(item)
    if not target:
        return []
    return [{"file": p["file"], "page": p["page"]} for p in pages_all if target in squash(p["text"])]
