"""Picks a Classifier based on router_config.json / PROVIDER env var.

Default: laya (free, no card required). Adjustable in router_config.json,
or override per-run with PROVIDER=jev in .env. See router/core/config.py
for the full precedence rules.
"""
from .classifiers import Classifier, JevClassifier, ClassifierError
from .laya_server import RemoteLayaClassifier
from . import config

ProviderError = ClassifierError  # kept as an alias: existing call sites catch this name

_instances = {}


def _provider_name() -> str:
    return config.get_provider()


def get_threshold() -> int:
    return config.get_confidence_threshold(_provider_name())


def get_classifier() -> Classifier:
    name = _provider_name()
    if name not in _instances:
        _instances[name] = JevClassifier() if name == "jev" else RemoteLayaClassifier()
    return _instances[name]


def classify_size(message: str, timeout: float = 3.0) -> dict:
    """Returns {"size", "confidence", "provider"}."""
    result = get_classifier().classify_size(message, timeout=timeout)
    result["provider"] = _provider_name()
    return result


def pick_skill(request: str, skills: list, timeout: float = 5.0) -> dict:
    """Returns {"skill", "confidence", "provider"} for one batch."""
    result = get_classifier().pick_skill_batch(request, skills, timeout=timeout)
    result["provider"] = _provider_name()
    return result
