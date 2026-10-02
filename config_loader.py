"""Loads config/companies.yaml + config/filters.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parent


def load_yaml(name: str) -> dict:
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_companies(only: list[str] | None = None, include_disabled: bool = False) -> dict[str, dict]:
    cfg = load_yaml("companies.yaml")
    defaults = cfg.get("defaults", {})
    out = {}
    for key, c in (cfg.get("companies") or {}).items():
        if only and key not in only:
            continue
        if not include_disabled and not c.get("enabled", False):
            continue
        if not c.get("collector"):
            continue
        out[key] = {**defaults, **c, "key": key, "name": c.get("name", key.title())}
    return out


def load_filters() -> dict:
    return load_yaml("filters.yaml")
