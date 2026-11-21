"""One-call baseline (EVAL.md section 3): one Argon call with all the plant's pages and the change.

The pages block is byte-identical to the long read's (same order, same headers), so the
automatic cache applies. Thinking low, structured output. Nothing else: no search, no
evidence check, no rules in code, no drawing.
"""

from __future__ import annotations

from app.reading import schemas
from app.reading.longread import pages_block

TASK = """

=== TASK ===
A proposed change to this plant (exactly as typed):
<<<{change}>>>

1. List every page above about the equipment this change concerns (file and page exactly as in each
   "=== file p.N ===" header).
2. List the values those pages give for it (attribute, value, unit, file, page, and the quote copied from the page).
3. Is the change safe? verdict: BLOCK (a check fails or documents disagree), REVIEW (something needed is
   missing), or "no conflicts found". why: one or two sentences.
"""


def one_call(models, pages_all: list[dict], change_text: str, usage: dict | None = None) -> dict:
    return models.call("one_call", pages_block(pages_all) + TASK.format(change=change_text), schemas.ONE_CALL,
                       "low", usage=usage)
