"""Add or remove this project's router hooks from a Claude Code
settings.json (project-level or user-level `~/.claude/settings.json`),
without touching anything else already in that file.

Usage:
    python -m core.py.tools.manage_hooks add    [target_settings_json_path]
    python -m core.py.tools.manage_hooks remove [target_settings_json_path]

With no path given, defaults to the user-level settings file
(~/.claude/settings.json), so the hooks apply in every directory.
"""
import json
import os
import sys

from .. import paths

ROOT = paths.ROOT.replace("\\", "/")
DEFAULT_TARGET = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

# Forward slashes and exec form (command + args, no shell) — Claude Code on
# Windows tells the model "Shell: PowerShell" but actually runs hooks under
# Git Bash (see github.com/anthropics/claude-code/issues/59225), so any
# shell-syntax command (cmd /c, PowerShell's Set-Location, &&, etc.) is a
# foot-gun. Exec form sidesteps the mismatch entirely: no shell is invoked.
# Windows: pythonw.exe, not python.exe, since a console build opens a terminal window on every hook run.
PYTHON_EXE = f"{ROOT}/.venv/Scripts/pythonw.exe" if os.name == "nt" else f"{ROOT}/.venv/bin/python"

# run_hook.py puts the project root on the path, so the hooks work from any working folder.
RUN_HOOK = f"{ROOT}/core/py/run_hook.py"
OUR_ARGS_LISTS = [
    [RUN_HOOK, "hooks.model_router.hook"],
    [RUN_HOOK, "hooks.skill_router.hook"],
]
HOOK_GROUPS = [
    ("UserPromptSubmit", "*", OUR_ARGS_LISTS, 10),
    ("PostToolUse", "Skill|Agent|Task", [[RUN_HOOK, "core.py.tools.log_followed"]], 5),
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


def _find_matcher_entry(hooks_list: list, matcher: str) -> dict:
    for entry in hooks_list:
        if entry.get("matcher") == matcher:
            return entry
    return None


def add(target: str):
    data = _load(target)
    data.setdefault("hooks", {})
    added = 0
    for event, matcher, args_lists, timeout in HOOK_GROUPS:
        hooks_list = data["hooks"].setdefault(event, [])
        entry = _find_matcher_entry(hooks_list, matcher)
        if entry is None:
            entry = {"matcher": matcher, "hooks": []}
            hooks_list.append(entry)
        existing = {(h.get("command"), tuple(h.get("args", [])))
                    for e in hooks_list if e.get("matcher") == matcher for h in e["hooks"]}
        for args in args_lists:
            if (PYTHON_EXE, tuple(args)) not in existing:
                entry["hooks"].append({"type": "command", "command": PYTHON_EXE, "args": args, "timeout": timeout})
                added += 1

    _save(target, data)
    print(f"Added {added} hook(s) to {target}" if added
          else f"Hooks already present in {target}, nothing to add.")


def remove(target: str):
    data = _load(target)
    removed = 0
    for event, matcher, args_lists, _ in HOOK_GROUPS:
        hooks_list = data.get("hooks", {}).get(event, [])
        our_keys = {(PYTHON_EXE, tuple(args)) for args in args_lists}
        for entry in hooks_list[:]:
            if entry.get("matcher") != matcher:
                continue
            before = len(entry["hooks"])
            entry["hooks"] = [h for h in entry["hooks"]
                              if (h.get("command"), tuple(h.get("args", []))) not in our_keys]
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


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("add", "remove"):
        print("Usage: python -m core.py.tools.manage_hooks add|remove [target_settings_json_path]")
        sys.exit(1)

    action = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TARGET

    if action == "add":
        add(target)
    else:
        remove(target)


if __name__ == "__main__":
    main()
