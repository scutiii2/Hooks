"""Add or remove this project's hooks in a Claude Code settings.json or a Codex hooks.json,
without touching anything else already in that file.

Usage:
    python -m core.py.tools.manage_hooks add    [--host claude|codex] [target_json_path]
    python -m core.py.tools.manage_hooks remove [--host claude|codex] [target_json_path]

With no path given, the user-level file of that host is used (~/.claude/settings.json for claude,
~/.codex/hooks.json for codex), so the hooks apply in every directory. Claude is the default host.

Codex only runs a hook after you trust it: after `add --host codex`, open Codex and review the new
hooks with /hooks.
"""
import json
import os
import subprocess
import sys

from .. import paths

ROOT = paths.ROOT.replace("\\", "/")
CLAUDE_TARGET = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
CODEX_TARGET = os.path.join(os.environ.get("CODEX_HOME", os.path.join(os.path.expanduser("~"), ".codex")), "hooks.json")

# Forward slashes and exec form (command + args, no shell) — Claude Code on
# Windows tells the model "Shell: PowerShell" but actually runs hooks under
# Git Bash (see github.com/anthropics/claude-code/issues/59225), so any
# shell-syntax command (cmd /c, PowerShell's Set-Location, &&, etc.) is a
# foot-gun. Exec form sidesteps the mismatch entirely: no shell is invoked.
# Windows: pythonw.exe, not python.exe, since a console build opens a terminal window on every hook run.
PYTHON_EXE = f"{ROOT}/.venv/Scripts/pythonw.exe" if os.name == "nt" else f"{ROOT}/.venv/bin/python"
# Codex has no `args` array, only a command string, so it gets the console build: stdout is certain to be captured.
CODEX_PYTHON = f"{ROOT}/.venv/Scripts/python.exe" if os.name == "nt" else PYTHON_EXE

# run_hook.py puts the project root on the path, so the hooks work from any working folder.
RUN_HOOK = f"{ROOT}/core/py/run_hook.py"


def _claude(args: list[str], timeout: int) -> dict:
    return {"type": "command", "command": PYTHON_EXE, "args": args, "timeout": timeout}


def _codex(*words: str, timeout: int, status: str = "") -> dict:
    """One command string; paths here use `/` and no spaces, so nothing needs shell quoting."""
    handler = {"type": "command", "command": subprocess.list2cmdline(list(words)), "timeout": timeout}
    return {**handler, "statusMessage": status} if status else handler


# (event, matcher or None, handlers). Same JSON shape for both hosts: event -> [{matcher, hooks: [...]}].
GROUPS = {
    "claude": [
        ("UserPromptSubmit", "*", [_claude([RUN_HOOK, "hooks.skill_router.hook"], 10)]),
        ("PostToolUse", "Skill", [_claude([RUN_HOOK, "core.py.tools.log_followed"], 5)]),
    ],
    # Not on Codex: log_followed (Codex has
    # no Skill tool call to match), noise_filter (its rewrite needs a Codex-only permissionDecision and
    # a POSIX shell that Codex on Windows may not use).
    "codex": [
        ("SessionStart", None, [
            _codex("node", f"{ROOT}/hooks/coding_rules/coding-rules-inject.js", timeout=10, status="Loading coding rules..."),
            _codex(CODEX_PYTHON, f"{ROOT}/hooks/token_economizer_patch/te_patch.py", timeout=10),
            _codex(CODEX_PYTHON, f"{ROOT}/hooks/source_of_truth/source_of_truth.py", timeout=10)]),
        ("UserPromptSubmit", None, [_codex(CODEX_PYTHON, RUN_HOOK, "hooks.skill_router.hook", "--host", "codex", timeout=10)]),
        ("PostToolUse", "apply_patch|Bash", [_codex(CODEX_PYTHON, f"{ROOT}/hooks/source_of_truth/source_of_truth.py", timeout=10)]),
    ],
}
DEFAULT_TARGET = {"claude": CLAUDE_TARGET, "codex": CODEX_TARGET}


def _key(handler: dict) -> tuple:
    return handler.get("command"), tuple(handler.get("args", []))


def _load(target: str) -> dict:
    if not os.path.exists(target):
        return {}
    with open(target, "r", encoding="utf-8") as f:
        content = f.read().strip()
    return json.loads(content) if content else {}


def _save(target: str, data: dict):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _find_matcher_entry(hooks_list: list, matcher) -> dict:
    for entry in hooks_list:
        if entry.get("matcher") == matcher:
            return entry
    return None


def add(target: str, host: str = "claude"):
    data = _load(target)
    data.setdefault("hooks", {})
    added = 0
    for event, matcher, handlers in GROUPS[host]:
        hooks_list = data["hooks"].setdefault(event, [])
        entry = _find_matcher_entry(hooks_list, matcher)
        if entry is None:
            entry = {"hooks": []} if matcher is None else {"matcher": matcher, "hooks": []}
            hooks_list.append(entry)
        existing = {_key(h) for e in hooks_list if e.get("matcher") == matcher for h in e["hooks"]}
        for handler in handlers:
            if _key(handler) not in existing:
                entry["hooks"].append(handler)
                added += 1

    _save(target, data)
    print(f"Added {added} hook(s) to {target}" if added
          else f"Hooks already present in {target}, nothing to add.")
    if added and host == "codex":
        print("Codex runs a hook only after you trust it: open Codex and review them with /hooks.")


def remove(target: str, host: str = "claude"):
    data = _load(target)
    removed = 0
    for event, matcher, handlers in GROUPS[host]:
        hooks_list = data.get("hooks", {}).get(event, [])
        our_keys = {_key(h) for h in handlers}
        for entry in hooks_list[:]:
            if entry.get("matcher") != matcher:
                continue
            before = len(entry["hooks"])
            entry["hooks"] = [h for h in entry["hooks"] if _key(h) not in our_keys]
            removed += before - len(entry["hooks"])
            if before and not entry["hooks"]:
                hooks_list.remove(entry)
        if event in data.get("hooks", {}) and not hooks_list:
            data["hooks"].pop(event)
    if not removed:
        print(f"No matching hooks found in {target}.")
        return
    if not data.get("hooks"):
        data.pop("hooks", None)

    _save(target, data)
    print(f"Removed {removed} hook(s) from {target}")


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    host = "claude"
    if "--host" in argv:
        i = argv.index("--host")
        host = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
    if not argv or argv[0] not in ("add", "remove") or host not in GROUPS:
        print("Usage: python -m core.py.tools.manage_hooks add|remove [--host claude|codex] [target_json_path]")
        sys.exit(1)

    target = argv[1] if len(argv) > 1 else DEFAULT_TARGET[host]
    (add if argv[0] == "add" else remove)(target, host)


if __name__ == "__main__":
    main()
