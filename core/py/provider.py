"""The classifier the routers use: Jev (TypeSafe API). Thresholds come from hooks/<hook>/config.json,
see core/py/config.py for the precedence rules.
"""
from .classifiers import JevClassifier
from . import config

NAME = "jev"
_classifier = JevClassifier()


def get_threshold(hook: str) -> int:
    return config.get_confidence_threshold(hook, NAME)


def classify_size(message: str, timeout: float = 3.0) -> dict:
    """Returns {"size", "confidence", "provider"}."""
    result = _classifier.classify_size(message, timeout=timeout)
    result["provider"] = NAME
    return result


def pick_skill(request: str, skills: list, timeout: float = 5.0) -> dict:
    """Returns {"skill", "confidence", "provider"} for one batch."""
    result = _classifier.pick_skill_batch(request, skills, timeout=timeout)
    result["provider"] = NAME
    return result
