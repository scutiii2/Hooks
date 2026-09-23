"""Classifier interface plus Jev (remote) and Laya (local) implementations.

Both size-classification and skill-picking are "pick one option from a
list, with a confidence score" — modeled here as one `ask_choice` method
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

        Returns {"choice": str, "confidence": int (0-100), "cost_usd": float}.
        Raises ClassifierError on any failure.
        """

    def classify_size(self, message: str, timeout: float = 3.0) -> dict:
        result = self.ask_choice(message, SIZE_CRITERIA, timeout)
        if result["choice"] not in SIZES:
            raise ClassifierError(f"unknown size: {result['choice']!r}")
        return {"size": result["choice"], "confidence": result["confidence"],
                "cost_usd": result["cost_usd"]}

    def pick_skill_batch(self, request: str, skills: list, timeout: float = 5.0) -> dict:
        criteria = {name: desc for name, desc in skills}
        criteria["none"] = "nothing here fits well"
        result = self.ask_choice(request, criteria, timeout)
        return {"skill": result["choice"], "confidence": result["confidence"],
                "cost_usd": result["cost_usd"]}


class JevClassifier(Classifier):
    """Remote, paid. typesafe-ai/jev via Vercel AI Gateway (OpenAI-compatible)."""

    GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
    MODEL_ID = "typesafe-ai/jev"
    INPUT_COST_PER_TOKEN = 0.042 / 1_000_000

    def _system_prompt(self, criteria: dict) -> str:
        options = " | ".join(criteria.keys())
        return (
            "You are a routing classifier. Given input and a set of named "
            f"options ({options}), pick exactly one option. "
            "Respond with ONLY a JSON object, no other text: "
            '{"choice": "<exact option name>", "confidence": <0-100 integer>}'
        )

    def ask_choice(self, subject: str, criteria: dict, timeout: float) -> dict:
        api_key = os.environ.get("AI_GATEWAY_API_KEY", "").strip()
        if not api_key:
            raise ClassifierError("AI_GATEWAY_API_KEY not set")

        criteria_lines = "\n".join(f"- {name}: {desc}" for name, desc in criteria.items())
        user_content = f"{subject}\n\nOptions:\n{criteria_lines}"

        payload = {
            "model": self.MODEL_ID,
            "messages": [
                {"role": "system", "content": self._system_prompt(criteria)},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.GATEWAY_URL,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
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
        except TimeoutError as e:
            raise ClassifierError(f"timeout: {e}") from e

        try:
            content = body["choices"][0]["message"]["content"]
            cost = body.get("usage", {}).get("prompt_tokens", 0) * self.INPUT_COST_PER_TOKEN
        except (KeyError, IndexError) as e:
            raise ClassifierError(f"unexpected response shape: {e}") from e

        try:
            parsed = json.loads(content)
            choice = parsed["choice"]
            confidence = int(parsed["confidence"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            raise ClassifierError(f"could not parse output: {content!r} ({e})") from e

        return {"choice": choice, "confidence": confidence, "cost_usd": cost}


class LayaClassifier(Classifier):
    """Local, free. https://github.com/NandhaKishorM/laya — pip install laya."""

    MODEL_ID = "convaiinnovations/laya"  # English-only checkpoint, pinned to
    # avoid Router() auto-downloading the multilingual model too.

    def __init__(self):
        self._agent = None

    def _get_router(self):
        if self._agent is None:
            try:
                import laya
            except ImportError as e:
                raise ClassifierError("laya not installed - pip install laya") from e
            try:
                self._agent = laya.load(self.MODEL_ID)
            except Exception as e:
                raise ClassifierError(f"failed to load Laya model: {e}") from e
        return self._agent

    def ask_choice(self, subject: str, criteria: dict, timeout: float) -> dict:
        agent = self._get_router()
        questions = {
            "choice": {
                "type": "choice",
                "instructions": "Pick the single best-fitting option.",
                "criteria": criteria,
            }
        }
        try:
            result = agent.predict({"input": subject}, questions)
            answer = result["answers"]["choice"]
            choice = answer["choice"]
            confidence = int(round(answer["confidence"] * 100))
        except ClassifierError:
            raise
        except Exception as e:
            raise ClassifierError(f"predict failed or unexpected response shape: {e}") from e

        return {"choice": choice, "confidence": confidence, "cost_usd": 0.0}
