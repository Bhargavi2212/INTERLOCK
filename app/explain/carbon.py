"""Step 8 (Carbon): which disagreeing page is likely right, and what goes wrong in the plant.
Text only: never changes a status, a value or the verdict. Runs only when documents disagree."""

from __future__ import annotations

import json

from app.reading import schemas
from app.reading.settings import reading_settings

PROMPT = """Plant documents disagree about equipment affected by a proposed change.

Change: <<<{change}>>>
Disagreements (attribute and the values each page states):
{disagreements}
Quotes behind the values:
{quotes}

For each disagreement: which page is likely right (file and page), why (from the quotes; say so if unclear),
and what goes wrong in the plant if the wrong one is built. Short, plain sentences. Do not invent values.
"""


def explain(models, change_text: str, disagreements: list[dict], values: list[dict]) -> list[dict]:
    attrs = {d["attribute"] for d in disagreements}
    quotes = [f"- {v['input']} = {v['value']} {v['unit']} ({v['file']} p.{v['page']}): \"{v['quote']}\""
              for v in values if v.get("evidence_ok") and v.get("input") in attrs]
    out = models.call("explain", PROMPT.format(change=change_text, disagreements=json.dumps(disagreements),
                                               quotes="\n".join(quotes)),
                      schemas.EXPLAIN, reading_settings()["thinking"]["explain"])
    return out.get("explanations", [])
