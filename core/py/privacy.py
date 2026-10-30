"""Prompts that mention secrets are never sent to the classifier (TypeSafe sees everything else).

Extra rules come from two optional JSON files with the same keys:
  global   <hooks root>/.privacy.json
  project  .claude/hooks-privacy.json in the working folder or the nearest parent
    "folders":  [paths]   global only: prompts from these folders (and below) are never sent
    "patterns": [regex]   prompts matching any are never sent (project patterns add to global ones)
    "private":  true|false  project only: true = nothing from this project is sent; false = ignore the
                            global folder rules here
    "inherit":  false     project only: ignore everything in the global file
The built-in secret detection always applies. A file that exists but cannot be read counts as private.
"""
import json
import os
import re

from .paths import ROOT

GLOBAL_FILE = os.path.join(ROOT, ".privacy.json")
PROJECT_FILE = os.path.join(".claude", "hooks-privacy.json")

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
    if re.fullmatch(r"(?:[A-Z]?[a-z]+)+\d{0,4}", blob):  # CamelCase words with a short numeric suffix
        return False
    # Needs all three classes: ordinary snake_case or CamelCase identifiers lack digits.
    return (any(c.isdigit() for c in blob) and any(c.islower() for c in blob)
            and any(c.isupper() for c in blob))


def _has_secret(text: str) -> bool:
    return PRIVATE_PATTERN.search(text) is not None or any(_looks_like_key(b) for b in BLOB_PATTERN.findall(text))


def _load(path: str) -> dict | None:
    """{} when the file is absent; None when it exists but is unreadable (callers treat that as private)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _project_file(cwd: str) -> str:
    folder = os.path.abspath(cwd)
    while True:
        candidate = os.path.join(folder, PROJECT_FILE)
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(folder)
        if parent == folder:
            return ""
        folder = parent


def _under(cwd: str, folders: list) -> bool:
    here = os.path.normcase(os.path.abspath(cwd))
    for f in folders:
        f = os.path.normcase(os.path.abspath(f))
        if here == f or here.startswith(f.rstrip(os.sep) + os.sep):
            return True
    return False


def _matches(patterns: list, text: str) -> bool:
    for p in patterns:
        try:
            if re.search(p, text, re.IGNORECASE):
                return True
        except re.error:
            continue  # a bad regex must not hide the others
    return False


def is_private(text: str, cwd: str = "") -> bool:
    if _has_secret(text):
        return True
    g = _load(GLOBAL_FILE)
    project = _project_file(cwd) if cwd else ""
    p = _load(project) if project else {}
    if g is None or p is None:
        return True
    inherit = p.get("inherit", True) is not False
    if not inherit:
        g = {}
    if _matches(list(g.get("patterns", [])) + list(p.get("patterns", [])), text):
        return True
    if isinstance(p.get("private"), bool):
        return p["private"]
    return bool(cwd) and _under(cwd, list(g.get("folders", [])))
