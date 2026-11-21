"""Eval runner gates and baselines (no network)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import eval_run  # noqa: E402
from app.store.memory import MemoryStore  # noqa: E402
from eval.baselines.keyword import keyword_pages  # noqa: E402
from eval.baselines.one_call import one_call  # noqa: E402


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    keys = tmp_path / "eval" / "keys"
    keys.mkdir(parents=True)
    (keys / "E1.json").write_text('{"id": "E1"}', encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "keys")
    return tmp_path


def plant_store(register=()):
    s = MemoryStore()
    pid = s.create_plant("eval")["plant_id"]
    s.mutate_plant(pid, lambda d: d.update(ingest_status="done", page_count=1))
    s.register[pid] = list(register)
    return s, pid


def test_gate_refuses_modified_key(repo):
    s, pid = plant_store()
    assert eval_run.preflight(s, pid, repo) is None
    (repo / "eval" / "keys" / "E1.json").write_text('{"id": "E1", "changed": true}', encoding="utf-8")
    assert "modified or uncommitted" in eval_run.preflight(s, pid, repo)


def test_gate_refuses_uncommitted_key(repo):
    s, pid = plant_store()
    (repo / "eval" / "keys" / "E9.json").write_text("{}", encoding="utf-8")
    assert "modified or uncommitted" in eval_run.preflight(s, pid, repo)


def test_gate_refuses_plant_with_register_entries(repo):
    s, pid = plant_store(register=[{"entry_id": "r1", "attribute": "installed", "value": 3}])
    assert "register" in eval_run.preflight(s, pid, repo)


def test_result_file_name_and_plant_id(tmp_path):
    (tmp_path / "eval" / "results").mkdir(parents=True)
    path = eval_run.result_path(tmp_path, "E", "E1", "one_call", 2)
    assert path.name == "E_E1_one_call_2.json"
    eval_run.write(path, "27d049ccd64f", "2026-11-21T15:00:00", 12.3, {"x": 1}, None)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["plant_id"] == "27d049ccd64f" and data["state"] == "done"


def test_keyword_baseline_item_string_only():
    pages = [{"n": 0, "file": "a.pdf", "page": 1, "text": "SG UNIT-1 FLOOR WASH WATER TRANSFER PUMPS"},
             {"n": 1, "file": "b.pdf", "page": 2, "text": "SG UNIT-1 FLR WASH WTR TRANSFER PUMPS"}]
    assert keyword_pages(pages, "SG Unit-1 floor wash water transfer pumps") == [{"file": "a.pdf", "page": 1}]
    assert keyword_pages(pages, "") == []


def test_one_call_prompt_starts_with_pages_block():
    from app.reading.longread import pages_block

    class Fake:
        def call(self, role, prompt, schema=None, thinking="low", usage=None):
            assert role == "one_call" and thinking == "low"
            assert prompt.startswith(pages_block(PAGES))     # same bytes as the long read: cache applies
            return {"pages": [], "values": [], "verdict": "REVIEW"}
    PAGES = [{"n": 0, "file": "a.pdf", "page": 1, "text": "x"}]
    assert one_call(Fake(), PAGES, "change")["verdict"] == "REVIEW"
