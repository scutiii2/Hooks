"""Loads router_config.json (adjustable settings), with .env overrides on top.

Precedence for any setting: matching .env var > router_config.json > the
hardcoded default below. This file is meant to be hand-edited.
"""
import json
import os

from .env_load import load_env
from .json_store import merge_defaults
from .paths import ROOT

load_env()

CONFIG_PATH = os.path.join(ROOT, "router_config.json")

DEFAULTS = {
    "confidence_threshold": {"jev": 60},
    "skill_picker_batch_size": 20,
}


def _read_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    return merge_defaults(data, DEFAULTS)


def get_confidence_threshold(provider_name: str = "jev") -> int:
    override = os.environ.get("CONFIDENCE_THRESHOLD", "").strip()
    if override:
        return int(override)
    thresholds = _read_config()["confidence_threshold"]
    return int(thresholds.get(provider_name, 60))


def get_skill_picker_batch_size() -> int:
    override = os.environ.get("SKILL_PICKER_BATCH_SIZE", "").strip()
    if override:
        return int(override)
    return int(_read_config()["skill_picker_batch_size"])
