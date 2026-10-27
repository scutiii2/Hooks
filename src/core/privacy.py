"""Prompts that mention secrets are never sent to the classifier (TypeSafe sees everything else)."""
import re

# Narrow on purpose: bare "key" or "token" would also skip ordinary talk about dictionaries and LLM tokens.
PRIVATE_PATTERN = re.compile(
    r"\.env\b|secret|passw(or)?d|api[ _-]?key|private[ _-]?key|ssh[ _-]?key|credential|"
    r"(access|auth|bearer|refresh)[ _-]?token|\bsk-[A-Za-z0-9]{8,}",
    re.IGNORECASE,
)


def is_private(text: str) -> bool:
    return PRIVATE_PATTERN.search(text) is not None
