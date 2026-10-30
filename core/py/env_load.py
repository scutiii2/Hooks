"""Minimal .env loader, no external deps.

Precedence: process environment > hooks/<hook>/.env > root .env.
"""
import os

from .paths import HOOKS, ROOT


def _read(path: str) -> dict:
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip():
                values[key.strip()] = value.strip()
    return values


def load_env(hook: str = ""):
    values = {**_read(os.path.join(ROOT, ".env")), **(_read(os.path.join(HOOKS, hook, ".env")) if hook else {})}
    for key, value in values.items():
        os.environ.setdefault(key, value)
