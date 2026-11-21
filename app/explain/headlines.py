"""Step 9 headlines (Hydrogen): one line per flagged/held result and per disagreement,
written from the result's own message. On failure the pipeline uses the rule messages."""

from __future__ import annotations

from app.reading import schemas
from app.reading.settings import reading_settings

PROMPT = """Write one short headline (max 15 words) for each finding below, for a plant engineer.
Keep every number and unit exactly as given. Do not add facts. Never say PASS.

{findings}
"""


def findings(after, disagreements, clashes) -> list[tuple[str, str]]:
    out = [(f"{r.rule_id}", f"{r.status}: {r.message}") for r in after if r.status != "OK"]
    out += [(f"disagree:{d['attribute']}", "documents disagree on " + d["attribute"] + ": " +
             "; ".join(f"{x['file']} p.{x['page']} = {x['value']}" for x in d["values"])) for d in disagreements]
    out += [(f"clash:{c['entry_id']}", f"clashes with approved change {c['entry_id']}: {c['attribute']} "
             f"approved {c['approved']}, proposed {c['proposed']}") for c in clashes]
    return out


def headlines(models, after, disagreements, clashes) -> list[str]:
    items = findings(after, disagreements, clashes)
    if not items:
        return []
    text = "\n".join(f"[{ref}] {msg}" for ref, msg in items)
    out = models.call("headlines", PROMPT.format(findings=text), schemas.HEADLINES,
                      reading_settings()["thinking"]["headlines"])
    by_ref = {h["ref"].strip("[]"): h["headline"] for h in out.get("headlines", [])}
    return [by_ref.get(ref, msg) for ref, msg in items]
