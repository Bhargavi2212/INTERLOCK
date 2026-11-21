"""The rule engine and the verdict never call a model or the network (CLAUDE.md)."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BANNED = ("google", "genai", "httpx", "requests", "urllib", "socket", "app.store", "aiohttp", "grpc")
FILES = sorted((ROOT / "app" / "rules").glob("*.py")) + sorted((ROOT / "app" / "verdict").glob("*.py"))


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_networked_imports(path):
    for name in imported_modules(path):
        assert not any(name == b or name.startswith(b + ".") for b in BANNED), f"{path.name} imports {name}"


def test_files_found():
    assert len(FILES) >= 6
