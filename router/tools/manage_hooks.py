"""Add or remove this project's router hooks from a Claude Code
settings.json (project-level or user-level `~/.claude/settings.json`),
without touching anything else already in that file.

Usage:
    python -m router.tools.manage_hooks add    [target_settings_json_path]
    python -m router.tools.manage_hooks remove [target_settings_json_path]

With no path given, defaults to the user-level settings file
(~/.claude/settings.json), so the hooks apply in every directory.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace("\\", "/")
DEFAULT_TARGET = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

# Forward slashes and exec form (command + args, no shell) — Claude Code on
# Windows tells the model "Shell: PowerShell" but actually runs hooks under
# Git Bash (see github.com/anthropics/claude-code/issues/59225), so any
# shell-syntax command (cmd /c, PowerShell's Set-Location, &&, etc.) is a
# foot-gun. Exec form sidesteps the mismatch entirely: no shell is invoked.
PYTHON_EXE = f"{ROOT}/.venv/Scripts/python.exe"

OUR_ARGS_LISTS = [
    ["-m", "router.model_router.hook"],
    ["-m", "router.skill_router.hook"],
]


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


def _find_matcher_entry(hooks_list: list) -> dict:
    for entry in hooks_list:
        if entry.get("matcher") == "*":
            return entry
    return None


def add(target: str):
    data = _load(target)
    data.setdefault("hooks", {})
    data["hooks"].setdefault("UserPromptSubmit", [])
    hooks_list = data["hooks"]["UserPromptSubmit"]

    entry = _find_matcher_entry(hooks_list)
    if entry is None:
        entry = {"matcher": "*", "hooks": []}
        hooks_list.append(entry)

    existing = {(h.get("command"), tuple(h.get("args", []))) for h in entry["hooks"]}
    added = 0
    for args in OUR_ARGS_LISTS:
        key = (PYTHON_EXE, tuple(args))
        if key not in existing:
            entry["hooks"].append({"type": "command", "command": PYTHON_EXE, "args": args, "timeout": 10})
            added += 1

    _save(target, data)
    print(f"Added {added} hook(s) to {target}" if added
          else f"Hooks already present in {target}, nothing to add.")


def remove(target: str):
    data = _load(target)
    hooks_list = data.get("hooks", {}).get("UserPromptSubmit", [])
    entry = _find_matcher_entry(hooks_list)

    if entry is None:
        print(f"No matching hooks found in {target}.")
        return

    our_keys = {(PYTHON_EXE, tuple(args)) for args in OUR_ARGS_LISTS}
    before = len(entry["hooks"])
    entry["hooks"] = [h for h in entry["hooks"]
                       if (h.get("command"), tuple(h.get("args", []))) not in our_keys]
    removed = before - len(entry["hooks"])

    # Clean up empty scaffolding so we don't leave clutter behind.
    if not entry["hooks"]:
        hooks_list.remove(entry)
    if not hooks_list:
        data["hooks"].pop("UserPromptSubmit", None)
    if not data.get("hooks"):
        data.pop("hooks", None)

    _save(target, data)
    print(f"Removed {removed} hook(s) from {target}" if removed
          else f"No matching hooks found in {target}.")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("add", "remove"):
        print("Usage: python -m router.tools.manage_hooks add|remove [target_settings_json_path]")
        sys.exit(1)

    action = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TARGET

    if action == "add":
        add(target)
    else:
        remove(target)


if __name__ == "__main__":
    main()
