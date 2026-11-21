"""Step 3: same item? Decisions API, one noul question per candidate page.

Batched so each call stays under the Decisions input limit. Threshold and
min_confidence from reading.yaml (set once on set A, frozen for set E).
Fallback (mode "names", or the API failing at runtime): keep candidates whose
text has a name and the unit tag.
"""

from __future__ import annotations

from app.reading.search import squash
from app.reading.settings import reading_settings

QUESTION = "Is page [{label}] about {item} ({system}), and not a similar item in another unit or system?"


def _batches(cands: list[dict], texts: dict, max_chars: int, max_pages: int):
    batch, size = [], 0
    for c in cands:
        t = texts.get((c["file"], c["page"]), "")
        if batch and (size + len(t) > max_chars or len(batch) >= max_pages):
            yield batch
            batch, size = [], 0
        batch.append(c)
        size += len(t)
    if batch:
        yield batch


def by_names(cands: list[dict], texts: dict, understanding: dict) -> list[dict]:
    names = [squash(n) for n in understanding.get("names", []) if squash(n)]
    tag = squash(understanding.get("unit_tag", ""))
    out = []
    for c in cands:
        s = squash(texts.get((c["file"], c["page"]), ""))
        keep = any(n in s for n in names) and (not tag or tag in s)
        out.append({**c, "same_item_p": None, "uncertain": False, "kept": keep})
    return out


def same_item(models, cands: list[dict], texts: dict, understanding: dict) -> tuple[list[dict], str, str]:
    """-> (candidates with kept / same_item_p / uncertain, mode used, note)."""
    cfg = reading_settings()["same_item"]
    if cfg["mode"] == "names":
        return by_names(cands, texts, understanding), "names", "names mode set in reading.yaml"
    est = reading_settings()["long_read"]["chars_per_token_estimate"]
    max_chars = cfg["max_input_tokens"] * est // 2  # half the limit: room for labels and questions
    out = []
    try:
        for batch in _batches(cands, texts, max_chars, cfg["max_pages_per_call"]):
            parts, questions = [f"Change concerns: {understanding.get('item')} ({understanding.get('system')})\n"], {}
            for i, c in enumerate(batch):
                label = f"P{i}"
                parts.append(f"\n[{label}] {c['file']} p.{c['page']}\n{texts.get((c['file'], c['page']), '')}\n")
                questions[label] = {"type": "noul", "instructions": QUESTION.format(
                    label=label, item=understanding.get("item"), system=understanding.get("system"))}
            answers = models.decide("".join(parts), questions)
            for i, c in enumerate(batch):
                a = answers.get(f"P{i}", {})
                p, conf = a.get("noul"), a.get("confidence")
                kept = p is not None and p >= cfg["threshold"]
                uncertain = conf is None or conf < cfg["min_confidence"]
                out.append({**c, "same_item_p": p, "uncertain": uncertain, "kept": kept or uncertain})
        return out, "decisions", ""
    except Exception as e:
        return by_names(cands, texts, understanding), "names", f"Decisions API failed ({type(e).__name__}); names fallback"
