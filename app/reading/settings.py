"""Loads app/reading/reading.yaml once."""

from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=1)
def reading_settings() -> dict:
    with open(Path(__file__).with_name("reading.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)
