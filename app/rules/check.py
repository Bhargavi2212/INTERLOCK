"""Runner the Managed Agent uses inside its sandbox (bundled with the rule engine; no model).

    cd /workspace/interlock && python -m app.rules.check /workspace/runs/<change_id>/try_<n>.json

A try file: {"inputs_by_rule": {rule: {input: value-dict}}, "limits": [doc-limit dicts],
"overrides": {input: {"value": ..., "unit": ...}}}. Overrides are the candidate fix (source
"fix") applied to every rule that uses that input. Prints the live rules' results as JSON.
The server never trusts this output: it re-runs everything itself (app/agent/recheck.py).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from app.rules.engine import run_rules
from app.rules.model import Value, doclimit_from_dict, value_from_dict

LEVER_RULE = {"line_nb": "R1", "installed": "R2"}   # each lever is one rule's input (PHASE_4 M3)
BUNDLE_FILES = ["app/__init__.py", "app/rules/__init__.py", "app/rules/engine.py", "app/rules/checks.py",
                "app/rules/units.py", "app/rules/model.py", "app/rules/check.py", "app/rules/rules.json"]


def hash_files(files: dict) -> str:
    """sha256 over (path, bytes) of the bundle, in path order. The server computes the same over
    the files it mounts; the runner over the files it finds. Catches accidental edits only: the
    guarantee is the server re-check on the server's own code."""
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode() + b"\0" + files[path] + b"\0")
    return h.hexdigest()


def bundle_sha256() -> str:
    root = Path(__file__).resolve().parents[2]
    return hash_files({p: (root / p).read_bytes() if (root / p).exists() else b"<missing>" for p in BUNDLE_FILES})


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
    return {"bundle_sha256": bundle_sha256(), "results": [{"rule_id": r.rule_id, "status": r.status, "value": r.value, "limit": r.limit,
                         "message": r.message} for r in results],
            "flagged": [r.rule_id for r in results if r.status == "flagged"],
            "held": [r.rule_id for r in results if r.status == "held"]}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), indent=1))
