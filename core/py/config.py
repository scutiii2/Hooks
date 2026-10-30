"""Reads hooks/<hook>/config.json (adjustable settings), with .env overrides on top.

Precedence for any setting: matching env var (hooks/<hook>/.env over the root .env) >
hooks/<hook>/config.json > the hardcoded default below. config.json is meant to be hand-edited.
"""
import json
import os

from .json_store import merge_defaults
from .paths import HOOKS

DEFAULTS = {
    "confidence_threshold": {"jev": 60},
    "skill_picker_batch_size": 20,
}


def _read_config(hook: str) -> dict:
    try:
        with open(os.path.join(HOOKS, hook, "config.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    return merge_defaults(data, DEFAULTS)


def get_confidence_threshold(hook: str, provider_name: str = "jev") -> int:
    override = os.environ.get("CONFIDENCE_THRESHOLD", "").strip()
    if override:
        return int(override)
    return int(_read_config(hook)["confidence_threshold"].get(provider_name, 60))


def get_skill_picker_batch_size() -> int:
    override = os.environ.get("SKILL_PICKER_BATCH_SIZE", "").strip()
    if override:
        return int(override)
    return int(_read_config("skill_router")["skill_picker_batch_size"])
