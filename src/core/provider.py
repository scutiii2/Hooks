"""The classifier the routers use: Jev (TypeSafe API). Thresholds come from router_config.json,
see src/core/config.py for the precedence rules.
"""
from .classifiers import Classifier, JevClassifier, ClassifierError
from . import config

ProviderError = ClassifierError  # kept as an alias: existing call sites catch this name

NAME = "jev"
_classifier = JevClassifier()


def get_threshold() -> int:
    return config.get_confidence_threshold(NAME)


def get_classifier() -> Classifier:
    return _classifier


def classify_size(message: str, timeout: float = 3.0) -> dict:
    """Returns {"size", "confidence", "provider"}."""
    result = get_classifier().classify_size(message, timeout=timeout)
    result["provider"] = NAME
    return result


def pick_skill(request: str, skills: list, timeout: float = 5.0) -> dict:
    """Returns {"skill", "confidence", "provider"} for one batch."""
    result = get_classifier().pick_skill_batch(request, skills, timeout=timeout)
    result["provider"] = NAME
    return result
