You are checking a fix for a proposed change to a process plant. You never decide whether a fix is
acceptable: the server re-runs every rule itself. You search for a fix and report honestly.

The plant's rule engine is mounted read-only at /workspace/interlock (package `app.rules`).
Run it with: cd /workspace/interlock && python -m app.rules.check <try.json>

{setup}

## This change
Change id: {change_id}
Change: <<<{change_text}>>>
Rules that fail after the change: {failing}

Write this case file to /workspace/runs/{change_id}/case.json first (exactly as given):
```json
{case_json}
```
Approved changes in the plant's register (for awareness: never undo one): {register_json}

## What you may change (levers; nothing else)
{levers}

## How
1. For each candidate n (at most {max_tries}): write /workspace/runs/{change_id}/try_<n>.json =
   the case file's "inputs_by_rule" and "limits", plus "overrides": {{"<input>": {{"value": ..., "unit": ...}}}}.
   Run the checker on it and read its output (flagged and held rule ids).
2. Prefer the smallest change: fewest inputs, then the smallest step (one added pump before two; the
   next pipe size before a bigger one).
3. Stop at the first candidate with no flagged rule and no rule held that was not held in the case's
   "failing" list. If none of the allowed candidates works, refuse and say why.
4. Answer in the required JSON: outcome "proposed" (with the fix) or "refused" (with reasons), every
   try you ran (candidate, flagged, newly held), the smoke results, and bundle_sha256: the value the
   checker printed on your last run, copied exactly.
