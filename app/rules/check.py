"""Runner the Managed Agent uses inside its sandbox (bundled with the rule engine; no model).

    cd /workspace/interlock && python -m app.rules.check /workspace/runs/<change_id>/try_<n>.json

A try file: {"inputs_by_rule": {rule: {input: value-dict}}, "limits": [doc-limit dicts],
"overrides": {input: {"value": ..., "unit": ...}}}. Overrides are the candidate fix (source
"fix") applied to every rule that uses that input. Prints the live rules' results as JSON.
The server never trusts this output: it re-runs everything itself (app/agent/recheck.py).
"""

from __future__ import annotations

import json
import sys

from app.rules.engine import run_rules
from app.rules.model import Value, doclimit_from_dict, value_from_dict

LEVER_RULE = {"line_nb": "R1", "installed": "R2"}   # each lever is one rule's input (PHASE_4 M3)


def run(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        t = json.load(f)
    inputs = {rule: {name: value_from_dict(v) for name, v in ins.items()}
              for rule, ins in t.get("inputs_by_rule", {}).items()}
    for name, o in (t.get("overrides") or {}).items():
        rule = LEVER_RULE.get(name)
        if rule is None:
            raise SystemExit(f"{name} is not a lever (allowed: {sorted(LEVER_RULE)})")
        inputs.setdefault(rule, {})[name] = Value(o["value"], o.get("unit", ""), quote="agent candidate",
                                                  source="fix")
    results = run_rules(inputs, [doclimit_from_dict(d) for d in t.get("limits", [])])
    return {"results": [{"rule_id": r.rule_id, "status": r.status, "value": r.value, "limit": r.limit,
                         "message": r.message} for r in results],
            "flagged": [r.rule_id for r in results if r.status == "flagged"],
            "held": [r.rule_id for r in results if r.status == "held"]}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), indent=1))
