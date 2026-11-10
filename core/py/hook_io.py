"""Stdin/stdout plumbing shared by the UserPromptSubmit hooks."""
import json
import re
import sys

from .privacy import is_private

SHORT_REPLY_PATTERN = re.compile(
    r"^\s*(yes|no|yeah|yep|nope|ok|okay|sure|do it|do that|make it|shorter|"
    r"longer|that|it|please|thanks|go ahead|sounds good)\b",
    re.IGNORECASE,
)


def is_short_contextual_reply(text: str) -> bool:
    words = text.strip().split()
    return len(words) <= 1 or (len(words) <= 6 and SHORT_REPLY_PATTERN.match(text) is not None)


def should_skip(prompt: str, cwd: str = "") -> bool:
    """Prompts never sent to the classifier: empty, short replies that only make sense in context, private."""
    return not prompt.strip() or is_short_contextual_reply(prompt) or is_private(prompt, cwd)


def read_payload() -> tuple[dict, str]:
    """Returns (hook payload, prompt text)."""
    payload = json.loads(sys.stdin.read().lstrip("﻿"))  # a BOM broke one run
    prompt = payload.get("prompt", "")
    if isinstance(prompt, dict):
        prompt = prompt.get("type", "") or ""
    return payload, prompt


def emit_tag(*tags: str):
    context = "\n".join(tags)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))
