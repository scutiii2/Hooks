"""Loads router_config.json (adjustable settings), with .env overrides on top.

Precedence for any setting: matching .env var > router_config.json > the
hardcoded default below. This file is meant to be hand-edited.
"""
import json
import os

from .env_load import load_env

load_env()

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(ROOT, "router_config.json")

DEFAULTS = {
    "provider": "laya",
    "confidence_threshold": {"jev": 60, "laya": 25},
    "skill_picker_batch_size": 20,
    "laya_url": "http://127.0.0.1:9120",
    "laya_strategy": "english-only",
}


def _read_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    for key, val in DEFAULTS.items():
        if isinstance(val, dict):
            data.setdefault(key, {})
            for sub_key, sub_val in val.items():
                data[key].setdefault(sub_key, sub_val)
        else:
            data.setdefault(key, val)
    return data


def get_provider() -> str:
    override = os.environ.get("PROVIDER", "").strip()
    if override:
        return override.lower()
    return _read_config()["provider"].strip().lower()


def get_confidence_threshold(provider_name: str) -> int:
    override = os.environ.get("CONFIDENCE_THRESHOLD", "").strip()
    if override:
        return int(override)
    thresholds = _read_config()["confidence_threshold"]
    return int(thresholds.get(provider_name, 60))


def get_laya_url() -> str:
    return os.environ.get("LAYA_URL", "").strip() or _read_config()["laya_url"]


def get_laya_strategy() -> str:
    return os.environ.get("LAYA_STRATEGY", "").strip() or _read_config()["laya_strategy"]


def get_skill_picker_batch_size() -> int:
    override = os.environ.get("SKILL_PICKER_BATCH_SIZE", "").strip()
    if override:
        return int(override)
    return int(_read_config()["skill_picker_batch_size"])
