"""Classifier interface plus the Jev implementation.

Both size-classification and skill-picking are "pick one option from a
list, with a confidence score" - modeled here as one `ask_choice` method
each classifier implements once, reused by both call sites.
"""
import json
import os
import urllib.request
import urllib.error
from abc import ABC, abstractmethod

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

        Returns {"choice": str, "confidence": int (0-100)}.
        Raises ClassifierError on any failure.
        """

    def classify_size(self, message: str, timeout: float = 3.0) -> dict:
        result = self.ask_choice(message, SIZE_CRITERIA, timeout)
        if result["choice"] not in SIZES:
            raise ClassifierError(f"unknown size: {result['choice']!r}")
        return {"size": result["choice"], "confidence": result["confidence"]}

    def pick_skill_batch(self, request: str, skills: list, timeout: float = 5.0) -> dict:
        criteria = {name: desc for name, desc in skills}
        criteria["none"] = "nothing here fits well"
        result = self.ask_choice(request, criteria, timeout)
        return {"skill": result["choice"], "confidence": result["confidence"]}


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
