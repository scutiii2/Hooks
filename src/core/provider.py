"""Picks a Classifier based on router_config.json / PROVIDER env var.

Default: laya (the LayaModel service, free), with Jev as the fallback when the service does not
answer. PROVIDER=jev uses Jev only. See router/core/config.py for the full precedence rules.
"""
from .classifiers import Classifier, FallbackClassifier, JevClassifier, LayaModelClassifier, ClassifierError
from . import config

ProviderError = ClassifierError  # kept as an alias: existing call sites catch this name

_instances = {}


def _provider_name() -> str:
    return config.get_provider()


def get_threshold(provider_name: str | None = None) -> int:
    """Threshold of the provider that answered (a Laya failure falls back to Jev); default: the configured one."""
    return config.get_confidence_threshold(provider_name or _provider_name())


def get_classifier() -> Classifier:
    name = _provider_name()
    if name not in _instances:
        _instances[name] = JevClassifier() if name == "jev" else FallbackClassifier(
            LayaModelClassifier(), "laya", JevClassifier(), "jev")
    return _instances[name]


def classify_size(message: str, timeout: float = 3.0) -> dict:
    """Returns {"size", "confidence", "provider"}."""
    result = get_classifier().classify_size(message, timeout=timeout)
    result["provider"] = result["provider"] or _provider_name()
    return result


def pick_skill(request: str, skills: list, timeout: float = 5.0) -> dict:
    """Returns {"skill", "confidence", "provider"} for one batch."""
    result = get_classifier().pick_skill_batch(request, skills, timeout=timeout)
    result["provider"] = result["provider"] or _provider_name()
    return result
