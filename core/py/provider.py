"""The classifier the router uses: Jev (TypeSafe API). Thresholds come from hooks/<hook>/config.json,
see core/py/config.py for the precedence rules.
"""
from .classifiers import JevClassifier
from . import config

NAME = "jev"
_classifier = JevClassifier()


def get_threshold(hook: str) -> int:
    return config.get_confidence_threshold(hook, NAME)


def pick_skill(request: str, skills: list, timeout: float = 5.0) -> dict:
    """Returns {"skill", "confidence", "provider"} for one batch."""
    result = _classifier.pick_skill_batch(request, skills, timeout=timeout)
    result["provider"] = NAME
    return result
