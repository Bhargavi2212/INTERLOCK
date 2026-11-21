"""Managed Agent flow with a fake models.agent (no network)."""

import json
import subprocess
import sys

import pytest

from app.agent import bundle, run as agent_run
from tests.test_agent_recheck import stored  # noqa: F401  (fixture)
from tests.test_drawing_pipeline import plant  # noqa: F401  (fixture)

GOOD_SMOKE = {"r1_velocity": 1.86}
THIRD_PUMP = {"outcome": "proposed",
              "fix": [{"input": "installed", "from": "2", "to": "3", "unit": "count", "why": "add a third pump"}],
              "tries": [{"n": 1, "candidate": "installed 3", "flagged": [], "newly_held": []}], "reasons": []}


class FakeAgent:
    def __init__(self, *answers, copied=None):
        self.answers, self.calls, self.copied = list(answers), [], copied

    def call(self, role, prompt, schema=None, thinking="low", usage=None):
        assert role == "agent_answer"
        if self.copied is None:
            raise RuntimeError("no copy")
        return self.copied

    def agent(self, prompt, environment, previous_id, schema, cfg):
        self.calls.append({"prompt": prompt, "environment": environment, "previous_id": previous_id})
        n = len(self.calls)
        return {"answer": self.answers.pop(0), "environment_id": "env-1" if isinstance(environment, dict) else environment,
                "interaction_id": f"int-{n}"}


def ans(base, smoke=GOOD_SMOKE, **kw):
    return {**base, "smoke": smoke, "bundle_sha256": bundle.bundle_hash(), **kw}


def test_first_fix_new_sandbox_then_reuse(stored):
    s, change = stored
    m = FakeAgent(ans(THIRD_PUMP), ans(THIRD_PUMP, smoke={"runs_listing": "c1/"}))
    first = agent_run.find_fix(s, m, change["change_id"])
    env = m.calls[0]["environment"]
    assert env["type"] == "remote" and m.calls[0]["previous_id"] is None
    targets = {x["target"] for x in env["sources"]}
    assert "/workspace/interlock/app/rules/engine.py" in targets and "/workspace/interlock/app/rules/rules.json" in targets
    assert first["outcome"] == "proposed" and first["recheck"]["proven"], first
    agent_state = s.get_plant(change["plant_id"])["agent"]
    assert agent_state["environment_id"] == "env-1" and agent_state["bundle_hash"] == bundle.bundle_hash()
    second = agent_run.find_fix(s, m, change["change_id"])
    assert m.calls[1]["environment"] == "env-1" and m.calls[1]["previous_id"] == "int-1"
    assert "list /workspace/runs/" in m.calls[1]["prompt"] and second["reused_sandbox"]
    assert second["runs_listing"] == "c1/"


def test_changed_rules_renew_sandbox(stored, monkeypatch):
    s, change = stored
    s.mutate_plant(change["plant_id"], lambda d: d.update(agent={"environment_id": "old", "last_interaction_id": "i0",
                                                               "bundle_hash": "stale", "persistent": True}))
    m = FakeAgent(ans(THIRD_PUMP))
    res = agent_run.find_fix(s, m, change["change_id"])
    assert isinstance(m.calls[0]["environment"], dict) and res["sandbox_note"] == "sandbox renewed: rules changed"


def test_persistent_off_fresh_every_time(stored, monkeypatch):
    s, change = stored
    off = {**agent_run.agent_cfg(), "persistent": False}
    monkeypatch.setattr(agent_run, "agent_cfg", lambda: off)
    m = FakeAgent(ans(THIRD_PUMP), ans(THIRD_PUMP))
    agent_run.find_fix(s, m, change["change_id"])
    agent_run.find_fix(s, m, change["change_id"])
    assert all(isinstance(c["environment"], dict) for c in m.calls)
    assert "agent" not in s.get_plant(change["plant_id"])


@pytest.mark.parametrize("answer,reason", [
    (ans({**THIRD_PUMP, "fix": [{"input": "installed", "to": "9", "unit": "count", "why": "x"}]}), "outside the allowed levers"),
    (ans({**THIRD_PUMP, "fix": [{"input": "line_role", "to": "pump discharge", "unit": "", "why": "x"}]}), "outside the allowed levers"),
    ({"something": "else"}, "agent answer unreadable"),
    (ans(THIRD_PUMP, bundle_sha256="0" * 64), "bundle changed in the sandbox"),
    (ans(THIRD_PUMP, bundle_sha256=""), "bundle hash not reported by the agent"),
    (ans(THIRD_PUMP, smoke={"r1_velocity": 3.71}), "smoke test failed"),
])
def test_bad_answers_refused(stored, answer, reason):
    s, change = stored
    res = agent_run.find_fix(s, FakeAgent(answer), change["change_id"])
    assert res["outcome"] == "refused" and reason in res["reasons"][0]
    assert res["recheck"] is None


def test_refusal_passes_reasons_through(stored):
    s, change = stored
    refusal = ans({"outcome": "refused", "fix": [], "tries": [{"n": 1, "candidate": "300 NB", "flagged": ["R1"],
                                                            "newly_held": []}],
                   "reasons": ["no allowed line size keeps velocity within the D5-200 limit for the line's role"]})
    res = agent_run.find_fix(s, FakeAgent(refusal), change["change_id"])
    assert res["outcome"] == "refused" and "D5-200" in res["reasons"][0] and res["tries"]


def test_bundle_only_rule_files_and_runner_works_alone(tmp_path):
    fs = bundle.files()
    assert set(fs) == {"app/__init__.py", "app/rules/__init__.py", "app/rules/engine.py", "app/rules/checks.py",
                       "app/rules/units.py", "app/rules/model.py", "app/rules/check.py", "app/rules/rules.json"}
    assert bundle.bundle_hash(fs) == bundle.bundle_hash()
    assert not any(b"GEMINI" in data or b".env" in data for data in fs.values())
    for path, data in fs.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(data)
    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps({"inputs_by_rule": {"R1": {
        "flow_total": {"value": 210, "unit": "m3/h", "source": "change"},
        "line_nb": {"value": 200, "unit": "NB", "source": "change"}}}, "limits": []}), encoding="utf-8")
    out = subprocess.run([sys.executable, "-m", "app.rules.check", str(smoke)], cwd=tmp_path,
                         capture_output=True, text=True, env={"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert out.returncode == 0, out.stderr
    printed = json.loads(out.stdout)
    r1 = printed["results"][0]
    assert r1["rule_id"] == "R1" and round(r1["value"], 2) == 1.86
    assert printed["bundle_sha256"] == bundle.bundle_hash()          # sandbox hash == server hash
    (tmp_path / "app" / "rules" / "checks.py").write_bytes(fs["app/rules/checks.py"] + b"# edited")
    edited = subprocess.run([sys.executable, "-m", "app.rules.check", str(smoke)], cwd=tmp_path,
                            capture_output=True, text=True,
                            env={"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert json.loads(edited.stdout)["bundle_sha256"] != bundle.bundle_hash()   # an edit is visible


def test_fix_route_needs_access_code(api, store):
    from fastapi.testclient import TestClient
    from app.api.main import app
    assert TestClient(app).post("/changes/x/fix").status_code == 401
    assert api.post("/changes/nope/fix").status_code == 404


def test_off_schema_answer_is_copied_into_the_schema_then_validated(stored):
    """Live 15:07: the agent's own answer did not hold to the schema (candidate an object);
    a structured copy of its answer is validated again and re-checked by the server."""
    s, change = stored
    off_schema = {"result": "fix found", "tries": [{"n": 1, "candidate": {"installed": {"value": 3, "unit": "count"}},
                                                    "flagged": [], "newly_held": []}]}
    m = FakeAgent(off_schema, copied=ans(THIRD_PUMP))
    res = agent_run.find_fix(s, m, change["change_id"])
    assert res["answer_read_by"] and res["outcome"] == "proposed" and res["recheck"]["proven"]
    assert res["bundle_note"] == "bundle hash reported by the agent; the server re-check decides"
    assert res["raw_answer"] and "fix found" in res["raw_answer"]
    assert isinstance(res["tries"][0]["candidate"], str)


def test_unreadable_even_after_copy(stored):
    s, change = stored
    res = agent_run.find_fix(s, FakeAgent({"x": 1}), change["change_id"])
    assert res["outcome"] == "refused" and "agent answer unreadable" in res["reasons"][0]


def test_agent_crash_is_stored_with_reason(stored):
    s, change = stored

    class Crash(FakeAgent):
        def agent(self, *a, **k):
            raise TimeoutError("slow")
    res = agent_run.find_fix(s, Crash(), change["change_id"])
    assert res["outcome"] == "refused" and "agent run failed (TimeoutError)" in res["reasons"][0]
    assert s.get_change(change["change_id"])["fix"]["reasons"] == res["reasons"]


def test_prose_answer_goes_to_the_copy(stored):
    """Live 15:16: the agent answered in prose (JSONDecodeError). answer None -> structured copy."""
    s, change = stored
    m = FakeAgent(None, copied=ans(THIRD_PUMP))
    res = agent_run.find_fix(s, m, change["change_id"])
    assert res["outcome"] == "proposed" and res["recheck"]["proven"]


def test_fenced_json_is_parsed():
    from app.reading.models import Models
    import types
    m = Models()
    fenced = "```json" + chr(10) + '{"outcome": "refused"}' + chr(10) + "```"
    inter = types.SimpleNamespace(status="completed", output_text=fenced, id="i1", environment_id="e1")
    m._stable = m._beta = types.SimpleNamespace(interactions=types.SimpleNamespace(create=lambda **k: inter))
    import os
    os.environ.setdefault("MANAGED_AGENT", "agent-test"); os.environ.setdefault("MODEL_NEON", "neon-test")
    from app import config
    config.get_settings.cache_clear()
    out = m.agent("p", {"type": "remote"}, None, {}, {"model_env": "MODEL_NEON", "max_total_tokens": 1,
                                                       "timeout_s": 5, "poll_s": 1})
    assert out["answer"] == {"outcome": "refused"}
