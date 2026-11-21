"""Rule engine: loads rules.yaml once and runs R1-R6. Never calls a model."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

RULES_PATH = Path(__file__).with_name("rules.yaml")


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> dict:
    with open(path or RULES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
