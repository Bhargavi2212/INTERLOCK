"""Step 4: pull the values (Argon), structured output, from the kept pages only,
plus the top design-basis pages (velocity tables) found by code search."""

from __future__ import annotations

import re

from app.reading import schemas
from app.reading.settings import reading_settings
from app.rules.engine import INPUT_QUANTITY

PROMPT = """Below are pages from a plant's documents about {item} ({system}), and design-basis pages.

{pages}

=== TASK ===
Copy the values these pages state for {item}, for these inputs only: {inputs}.
Rules (all of them):
- Copy every value exactly as printed; the quote is the sentence or table row copied character for character
  from that page. Never compute, never convert units, never guess. If a value is not on the pages, leave it out.
- A count of pumps: give it as the digits printed in its quote (e.g. "2" from "Two (2W) nos.") with the unit as
  printed ("nos.") or "count".
- arrangement: the working/standby text as printed (e.g. "1W+1S", "2W", "3X100%").
- installed: total pumps installed; working: pumps working; flow_per_pump: rated capacity of one pump.
- service: ONLY the data sheet's "Fluid to be handled" value, with a quote that contains "Fluid to be handled".
  Never use the item's name as the service.
- line_nb: the discharge line size of these pumps (e.g. "200" with unit "NB"); line_role: "pump discharge",
  "discharge header" or "pump suction" only if the page says so.
- volume: the sump's effective (working) capacity.
- limits: design-basis velocity limits (e.g. "pump discharge 50-150 mm 1.8-2.4 m/s") as rule_id "R1",
  name "velocity_band", low, high, unit, applies_from_nb, applies_to_nb (omit for "and above"), applies_to
  (e.g. "pump discharge", "pump suction", "discharge header"), with the quote.
- shared_discharge: only if a page states in text whether these pumps discharge into one common header/line
  (value true) or separate lines (value false), with the quote. Otherwise leave it empty.
- file and page exactly as in each page's "=== file p.N ===" header.
"""

VELOCITY = re.compile(r"velocit", re.I)
MS = re.compile(r"m\s*/\s*s(?:ec)?\b", re.I)


def design_basis_pages(pages_all: list[dict], exclude: set, top: int) -> list[dict]:
    scored = []
    for p in pages_all:
        if (p["file"], p["page"]) in exclude:
            continue
        v, m = len(VELOCITY.findall(p["text"])), len(MS.findall(p["text"]))
        if v and m:
            scored.append((v + m, p))
    scored.sort(key=lambda x: (-x[0], x[1]["n"]))
    return [p for _, p in scored[:top]]


def pull_values(models, understanding: dict, kept: list[dict], pages_all: list[dict]) -> dict:
    cfg = reading_settings()
    by_key = {(p["file"], p["page"]): p for p in pages_all}
    keys = {(c["file"], c["page"]) for c in kept}
    basis = design_basis_pages(pages_all, keys, cfg["values"]["design_basis_pages"])
    blocks = [f"=== {k[0]} p.{k[1]} ===\n{by_key[k]['text']}\n" for k in sorted(keys, key=lambda k: by_key[k]["n"])
              if k in by_key]
    blocks += [f"=== {p['file']} p.{p['page']} === (design basis)\n{p['text']}\n" for p in basis]
    prompt = PROMPT.format(item=understanding.get("item"), system=understanding.get("system"),
                           pages="".join(blocks), inputs=", ".join(sorted(INPUT_QUANTITY)))
    out = models.call("values", prompt, schemas.VALUES, cfg["thinking"]["values"])
    out["design_basis_pages"] = [{"file": p["file"], "page": p["page"]} for p in basis]
    return out
