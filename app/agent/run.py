"""Find a fix: the Managed Agent in the plant's persistent sandbox, then the server re-check.

- New sandbox (first fix on the plant, or rules changed, or persistent off): the rules bundle is
  mounted read-only; the agent first runs a smoke test (R1 210 m3/h in 200 NB -> 1.86 m/s) and
  tries a write under /workspace/interlock/app/rules/, which must FAIL. Otherwise: stop,
  "bundle not read-only" (or "smoke test failed"), nothing trusted, sandbox not kept.
- Same plant later: environment_id + previous_interaction_id reused; the agent lists
  /workspace/runs/ first (earlier fixes are still there: persistence, shown on screen).
- A changed bundle hash creates a NEW sandbox; the result says "sandbox renewed: rules changed".
- The answer is validated (fields, levers); then app/agent/recheck.py decides. The agent never does.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

import yaml

from app.agent import bundle
from app.agent.levers import allowed, base_installed, levers
from app.agent.recheck import rebuild, recheck
from app.reading import schemas
from app.reading.models import EXTRACT_PROMPT
from app.rules.model import doclimit_to_dict, value_to_dict
from app.reading.scenario import doc_limits

HERE = Path(__file__).parent

NEW_SETUP = """## Setup (new sandbox) — do this first
a. Run the smoke test: write /workspace/smoke.json = {{"inputs_by_rule": {{"R1": {{"flow_total": {{"value": {flow}, "unit": "m3/h", "source": "change"}}, "line_nb": {{"value": {nb}, "unit": "NB", "source": "change"}}}}}}}}, limits [] ;
   run the checker on it; report R1's value as smoke.r1_velocity.
b. Try to write a file /workspace/interlock/app/rules/_write_test.txt. Report smoke.write_blocked = true only if the
   write FAILED. Do not change permissions or anything under /workspace/interlock yourself."""
REUSED_SETUP = """## Setup (this plant's sandbox, used before)
First list /workspace/runs/ and report it as smoke.runs_listing (earlier fixes for this plant are kept there)."""


@lru_cache(maxsize=1)
def agent_cfg() -> dict:
    with open(HERE / "agent.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_case(store, change: dict) -> dict:
    built = rebuild(store, change)
    return {
        "change_id": change["change_id"], "change": change["text"],
        "inputs_by_rule": {rule: {k: value_to_dict(v) for k, v in ins.items()} for rule, ins in built["sc"]["after"].items()},
        "limits": [doclimit_to_dict(d) for d in doc_limits(change.get("limits") or [])],
        "failing": [r["rule_id"] for r in change.get("results_after", []) if r["status"] in ("flagged", "held")],
    }


def lever_text(base: float | None) -> str:
    lv = levers()
    inst = (f"installed: {base:g} + one of {lv['installed']['add']} (unit count)" if base is not None
            else "installed: not available (the documents disagree on the installed count)")
    return f"- line_nb: one of {lv['line_nb']['sizes']} (unit NB)\n- {inst}\n- nothing else"


def validate(answer) -> tuple[bool, str]:
    if not isinstance(answer, dict) or answer.get("outcome") not in ("proposed", "refused"):
        return False, "agent answer unreadable"
    for f in answer.get("fix") or []:
        if not isinstance(f, dict) or "input" not in f or "to" not in f:
            return False, "agent answer unreadable"
    if answer["outcome"] == "proposed" and not answer.get("fix"):
        return False, "agent answer unreadable"
    return True, ""


def find_fix(store, models, change_id: str, progress=lambda step: None) -> dict:
    cfg = agent_cfg()
    t0 = time.monotonic()
    change = store.get_change(change_id)
    plant_id = change["plant_id"]
    state = (store.get_plant(plant_id) or {}).get("agent") or {}
    progress("prepare")
    fs = bundle.files()
    h = bundle.bundle_hash(fs)
    reuse = bool(cfg["persistent"] and state.get("environment_id") and state.get("bundle_hash") == h)
    renewed = bool(cfg["persistent"] and state.get("environment_id") and state.get("bundle_hash") != h)
    environment = state["environment_id"] if reuse else {"type": "remote", "sources": bundle.sources(fs)}
    register = store.list_register(plant_id)
    case = build_case(store, change)
    smoke = cfg["smoke"]
    prompt = (HERE / "prompt.md").read_text(encoding="utf-8").format(
        setup=REUSED_SETUP if reuse else NEW_SETUP.format(flow=smoke["flow_m3h"], nb=smoke["line_nb"]),
        change_id=change_id, change_text=change["text"], failing=", ".join(case["failing"]) or "none",
        case_json=json.dumps(case), register_json=json.dumps(register, default=str),
        levers=lever_text(base_installed(change, register)), max_tries=cfg["max_tries"])

    progress("agent")
    out = models.agent(prompt, environment, state.get("last_interaction_id") if reuse else None,
                       schemas.AGENT_ANSWER, cfg)
    answer = out["answer"]
    result = {"outcome": "refused", "fix": [], "tries": (answer or {}).get("tries", []) if isinstance(answer, dict) else [],
              "reasons": [], "recheck": None, "environment_id": out.get("environment_id"),
              "persistent": cfg["persistent"], "reused_sandbox": reuse,
              "sandbox_note": "sandbox renewed: rules changed" if renewed else "",
              "runs_listing": None}

    progress("read answer")
    result["raw_answer"] = out.get("raw") or (json.dumps(answer, default=str)[:6000] if answer is not None else None)
    ok, why = validate(answer)
    if not ok:
        # The agent did not hold to the schema: one structured call copies its own answer into it
        # (never invents), then the same validation runs again (PHASE_4 2.3 fallback).
        try:
            answer = models.call("agent_answer", EXTRACT_PROMPT + (result["raw_answer"] or ""),
                                 schemas.AGENT_ANSWER, "low")
            result["answer_read_by"] = "structured copy of the agent's answer"
            result["tries"] = answer.get("tries", result["tries"]) if isinstance(answer, dict) else result["tries"]
            ok, why = validate(answer)
        except Exception as e:  # noqa: BLE001
            ok, why = False, f"agent answer unreadable ({type(e).__name__})"
    if ok and not reuse:
        s = answer.get("smoke") or {}
        if not s.get("write_blocked"):
            ok, why = False, "bundle not read-only"
        elif abs(float(s.get("r1_velocity") or 0) - smoke["velocity"]) > smoke["tolerance"]:
            ok, why = False, f"smoke test failed: R1 {s.get('r1_velocity')} m/s, expected {smoke['velocity']}"
    if isinstance(answer, dict):
        result["runs_listing"] = (answer.get("smoke") or {}).get("runs_listing")
        result["tries"] = [{**t, "candidate": t["candidate"] if isinstance(t.get("candidate"), str)
                            else json.dumps(t.get("candidate"))} for t in (answer.get("tries") or [])
                           if isinstance(t, dict)] or result["tries"]
    if not ok:
        result["reasons"] = [why]
    else:
        if cfg["persistent"]:   # keep the sandbox only once it is proven sound
            store.mutate_plant(plant_id, lambda d: d.update(agent={
                "environment_id": out.get("environment_id") or state.get("environment_id"),
                "last_interaction_id": out.get("interaction_id"), "bundle_hash": h, "persistent": True}))
        result["reasons"] = answer.get("reasons", [])
        if answer["outcome"] == "proposed":
            lev_ok, lev_why = allowed(answer["fix"], base_installed(change, register))
            if not lev_ok:
                result["reasons"] = [lev_why]
            else:
                progress("server re-check")
                result.update(outcome="proposed", fix=answer["fix"], recheck=recheck(store, change, answer["fix"]))
    result["seconds"] = round(time.monotonic() - t0, 1)
    change["fix"] = result
    store.put_change(plant_id, change_id, change)
    return result
