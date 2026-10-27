"""Classifier interface plus Jev (TypeSafe API), LayaModel (HTTP service) and a Laya-then-Jev fallback.

Both size-classification and skill-picking are "pick one option from a
list, with a confidence score" — modeled here as one `ask_choice` method
each classifier implements once, reused by both call sites.
"""
import json
import os
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod

from . import config
from .env_load import load_env

load_env()

SIZES = ["tiny", "everyday", "large", "hardest"]
SIZE_CRITERIA = {
    "tiny": "a lookup, a rename, a one-line answer",
    "everyday": "a normal email, post, or short document",
    "large": "a multi-step build, research, a full report",
    "hardest": "strategy, or anything where a wrong call is expensive",
}


class ClassifierError(Exception):
    pass


class Classifier(ABC):
    """One question: which of these named options fits best, and how sure?"""

    @abstractmethod
    def ask_choice(self, subject: str, criteria: dict, timeout: float) -> dict:
        """criteria: {option_name: one_line_description}.

        Returns {"choice": str, "confidence": int (0-100)}, plus "provider" when
        the answerer is not fixed (see FallbackClassifier).
        Raises ClassifierError on any failure.
        """

    def classify_size(self, message: str, timeout: float = 3.0) -> dict:
        result = self.ask_choice(message, SIZE_CRITERIA, timeout)
        if result["choice"] not in SIZES:
            raise ClassifierError(f"unknown size: {result['choice']!r}")
        return {"size": result["choice"], "confidence": result["confidence"], "provider": result.get("provider")}

    def pick_skill_batch(self, request: str, skills: list, timeout: float = 5.0) -> dict:
        criteria = {name: desc for name, desc in skills}
        criteria["none"] = "nothing here fits well"
        result = self.ask_choice(request, criteria, timeout)
        return {"skill": result["choice"], "confidence": result["confidence"], "provider": result.get("provider")}


class JevClassifier(Classifier):
    """Remote, paid. TypeSafe's own Jev API (POST /v1/systemone): typed question, real probabilities."""

    URL = "https://api.typesafe.ai/v1/systemone"
    MODEL_ID = "jev-latest"
    KEY_ENV = "TYPESAFE_API_KEY"
    QUESTION_ID = "answer"

    def ask_choice(self, subject: str, criteria: dict, timeout: float) -> dict:
        api_key = os.environ.get(self.KEY_ENV, "").strip()
        if not api_key:
            raise ClassifierError(f"{self.KEY_ENV} not set")

        payload = {
            "state": subject,
            "model": self.MODEL_ID,
            "questions": {self.QUESTION_ID: {
                "type": "choice",
                "instructions": "Pick the single best-fitting option.",
                "criteria": criteria,
            }},
        }
        req = urllib.request.Request(
            self.URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise ClassifierError(f"HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ClassifierError(f"request failed: {e}") from e
        except (TimeoutError, ValueError) as e:
            raise ClassifierError(f"timeout or bad JSON: {e}") from e

        try:
            answer = body["answers"][self.QUESTION_ID]
            choice = answer["choice"]
            confidence = answer["confidence"]
        except (KeyError, TypeError, AttributeError) as e:
            raise ClassifierError(f"unexpected response shape: {e}") from e
        if choice not in criteria:
            raise ClassifierError(f"answer names an option that was not offered: {choice!r}")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ClassifierError(f"no usable confidence: {confidence!r}")

        return {"choice": choice, "confidence": round(confidence * 100)}


class LayaModelClassifier(Classifier):
    """LayaModel (the shared Laya HTTP service, often on another device): POST /v1/ask, token in LAYA_TOKEN."""

    QUESTION_ID = "choice"

    def __init__(self, url: str | None = None, strategy: str | None = None):
        self.url = (url or config.get_laya_url()).rstrip("/")
        self.strategy = strategy or config.get_laya_strategy()

    def ask_choice(self, subject: str, criteria: dict, timeout: float) -> dict:
        payload = {
            "strategy": self.strategy,
            "text": subject,
            "questions": {self.QUESTION_ID: {
                "type": "choice",
                "instructions": "Pick the single best-fitting option.",
                "criteria": criteria,
            }},
        }
        headers = {"Content-Type": "application/json"}
        token = os.environ.get("LAYA_TOKEN", "").strip()
        if token:
            headers["X-Internal-Token"] = token
        req = urllib.request.Request(
            f"{self.url}/v1/ask", data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ClassifierError(f"laya HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}") from e
        except urllib.error.URLError as e:
            raise ClassifierError(f"laya unreachable at {self.url}: {e.reason}") from e
        except (TimeoutError, OSError, ValueError) as e:
            raise ClassifierError(f"laya timeout or bad JSON: {e}") from e

        try:
            answer = body["answers"][self.QUESTION_ID]
            choice = answer["choice"]
            confidence = answer["answer_confidence"]
        except (KeyError, TypeError) as e:
            raise ClassifierError(f"laya unexpected response shape: {e}") from e
        if choice not in criteria:
            raise ClassifierError(f"laya answered an option that was not offered: {choice!r}")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ClassifierError(f"laya gave no usable confidence: {confidence!r}")

        return {"choice": choice, "confidence": round(confidence * 100), "provider": "laya"}


class FallbackClassifier(Classifier):
    """Ask the primary; on ClassifierError ask the fallback with what is left of the timeout.

    Answers carry the provider that gave them, so callers apply that provider's confidence threshold.
    """

    PRIMARY_SHARE = 0.5  # of the timeout; an unreachable primary must not eat the fallback's time

    def __init__(self, primary: Classifier, primary_name: str, fallback: Classifier, fallback_name: str):
        self.primary, self.primary_name = primary, primary_name
        self.fallback, self.fallback_name = fallback, fallback_name
        self._primary_down = False  # shortcut: per process (one hook run), so one skill-picker run tries it once

    def ask_choice(self, subject: str, criteria: dict, timeout: float) -> dict:
        start = time.monotonic()
        if not self._primary_down:
            try:
                result = self.primary.ask_choice(subject, criteria, timeout * self.PRIMARY_SHARE)
                return {**result, "provider": self.primary_name}
            except ClassifierError:
                self._primary_down = True
        result = self.fallback.ask_choice(subject, criteria, max(timeout - (time.monotonic() - start), 0.5))
        return {**result, "provider": self.fallback_name}
