"""No limit or unit factor is written in Python (CLAUDE.md): they live in rules.yaml."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {0, 1, 2, 4, 60, 100, 1000, 3600}  # counts, pi/4, D^2, min/h, %, mg->kg, s/h
FILES = [ROOT / "app" / "rules" / "checks.py", ROOT / "app" / "rules" / "units.py"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_only_allowed_numeric_literals(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert found <= ALLOWED, f"{path.name} has numeric literals {sorted(found - ALLOWED)}"
