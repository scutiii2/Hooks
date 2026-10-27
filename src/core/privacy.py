"""Prompts that mention secrets are never sent to the classifier (TypeSafe sees everything else)."""
import re

# Narrow on purpose: bare "key" or "token" would also skip ordinary talk about dictionaries and LLM tokens.
PRIVATE_PATTERN = re.compile(
    r"\.env\b|secret|passw(or)?d|api[ _-]?key|private[ _-]?key|ssh[ _-]?key|credential|"
    r"(access|auth|bearer|refresh)[ _-]?token|\bsk-[A-Za-z0-9]{8,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY|\b(ghp|gho|ghs|github_pat|xox[abprs]|AKIA|AIza)[_-]?[A-Za-z0-9]{12,}|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.",
    re.IGNORECASE,
)
# Key-shaped blobs with no giveaway word: one unbroken run of 24+ base64/url-safe characters.
BLOB_PATTERN = re.compile(r"(?<![\w/.\-])[A-Za-z0-9_+=-]{24,}(?![\w/.\-])")


def _looks_like_key(blob: str) -> bool:
    if re.fullmatch(r"[0-9a-fA-F]+", blob):  # git SHAs and plain hashes are common and harmless
        return False
    # Needs all three classes: ordinary snake_case or CamelCase identifiers lack digits.
    return (any(c.isdigit() for c in blob) and any(c.islower() for c in blob)
            and any(c.isupper() for c in blob))


def is_private(text: str) -> bool:
    return PRIVATE_PATTERN.search(text) is not None or any(_looks_like_key(b) for b in BLOB_PATTERN.findall(text))
