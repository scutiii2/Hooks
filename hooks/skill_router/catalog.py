"""The skills the picker chooses from: every SKILL.md found on this machine, plus the built-ins.

Scanned fresh on each import (the hook is a new process per prompt), so plugin updates are picked up
without any edit here. ~/.claude/skills is not scanned: here it only mirrors the remote anthropic-skills:*, which builtins.py
lists under their real prefixed names. Built-in and remote skills have no usable file; see builtins.py.
"""
import glob
import json
import os

from .builtins import BUILTINS

HOME = os.path.join(os.path.expanduser("~"), ".claude")
MAX_DESCRIPTION = 160


def installed_plugins() -> dict[str, str]:
    """{plugin name: install path}."""
    path = os.path.join(HOME, "plugins", "installed_plugins.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        plugins = json.load(f).get("plugins", {})
    return {key.split("@")[0]: entries[0]["installPath"] for key, entries in plugins.items() if entries}


def parse_frontmatter(text: str) -> dict[str, str]:
    """`name` and `description` from a SKILL.md header; handles quoted and `>` / `|` block values."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields, key = {}, None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line[:1] in (" ", "\t") and key:
            fields[key] = f"{fields[key]} {line.strip()}".strip()
        elif ":" in line:
            key, _, value = line.partition(":")
            value = value.strip()
            fields[key] = "" if value in (">", "|", ">-", "|-") else value.strip("\"'")
    return fields


def one_line(description: str) -> str:
    """First sentence, capped; the picker sends every description to the classifier."""
    sentence = description.split(". ")[0].rstrip(".")
    return sentence if len(sentence) <= MAX_DESCRIPTION else sentence[:MAX_DESCRIPTION - 3] + "..."


def skills_in(skills_dir: str, prefix: str = "") -> dict[str, str]:
    found = {}
    for path in glob.glob(os.path.join(skills_dir, "**", "SKILL.md"), recursive=True):
        try:
            with open(path, encoding="utf-8") as f:
                fields = parse_frontmatter(f.read())
        except (OSError, UnicodeDecodeError):
            continue
        if fields.get("disable-model-invocation") == "true":
            continue  # Claude never picks these on its own, so suggesting them would be noise
        name = fields.get("name") or os.path.basename(os.path.dirname(path))
        found[prefix + name] = one_line(fields.get("description", ""))
    return found


def load_skills() -> list[tuple[str, str]]:
    found = dict(BUILTINS)
    for name, path in installed_plugins().items():
        found.update(skills_in(os.path.join(path, "skills"), f"{name}:"))
    folder = os.getcwd()
    while True:
        found.update(skills_in(os.path.join(folder, ".claude", "skills")))
        parent = os.path.dirname(folder)
        if parent == folder:
            return list(found.items())
        folder = parent


SKILLS = load_skills()
