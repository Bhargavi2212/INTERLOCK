"""The read-only rules bundle mounted into the agent's sandbox (PHASE_4 M1, D2).

Only the rule engine: app/__init__.py, app/rules/{__init__,engine,checks,units,model,check}.py and
rules.json (rules.yaml as JSON, so the sandbox needs no pyyaml). No key, no .env, nothing
outside app/rules. Mounted with environment.sources (inline, base64) under /workspace/interlock/.
The hash (sha256 over paths and bytes) decides sandbox renewal: a changed hash -> new sandbox.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from app.rules.engine import load_rules

APP = Path(__file__).resolve().parents[1]
ROOT_IN_SANDBOX = "/workspace/interlock"
RULE_FILES = ["__init__.py", "engine.py", "checks.py", "units.py", "model.py", "check.py"]


def files() -> dict[str, bytes]:
    out = {"app/__init__.py": b""}
    for name in RULE_FILES:
        out[f"app/rules/{name}"] = (APP / "rules" / name).read_bytes()
    out["app/rules/rules.json"] = json.dumps(load_rules(), indent=1, sort_keys=True).encode("utf-8")
    return out


def bundle_hash(fs: dict[str, bytes] | None = None) -> str:
    fs = fs or files()
    h = hashlib.sha256()
    for path in sorted(fs):
        h.update(path.encode() + b"\0" + fs[path] + b"\0")
    return h.hexdigest()


def sources(fs: dict[str, bytes] | None = None) -> list[dict]:
    fs = fs or files()
    return [{"type": "inline", "encoding": "base64", "content": base64.b64encode(data).decode("ascii"),
             "target": f"{ROOT_IN_SANDBOX}/{path}"} for path, data in sorted(fs.items())]
