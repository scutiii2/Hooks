#!/usr/bin/env python3
"""HidePluginWindows: stop plugin hooks from opening a terminal window on Windows.

Plugin hooks (tokeneconomizer, superpowers, caveman, ponytail) run `sh`, `cmd` or `node` straight
from Claude Code, which has no console, so each run flashes a window. On SessionStart this wraps every
command hook of the installed plugins in `pythonw run_hidden.py bash -c '<command>'`, which runs it
with no window and relays stdin, stdout and the exit code. It also gives the hook a status message
naming its plugin, so the label Claude Code shows says where the hook comes from.

A plugin update restores the original files; the next session start wraps them again, so the first
session after an update can still flash. Safe to run twice: wrapped commands are skipped.

    py hide_plugin_windows.py    wrap now, print what changed
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "plugins" / "cache"
RUN_HIDDEN = (ROOT / "core" / "py" / "run_hidden.py").as_posix()
# cache/<marketplace>/<plugin>/<version>/... holds each plugin's hook files
PATTERNS = ("*/*/*/hooks/hooks.json", "*/*/*/hooks/claude-*.json", "*/*/*/.claude-plugin/plugin.json")
GIT_BASH = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"


def wrap(command: str, pythonw: str, bash: str) -> str:
    # the leading space makes Windows quote the argument whole; without it a command that starts
    # with a quote reaches bash cut in half
    return " ".join([f'"{pythonw}"', f'"{RUN_HIDDEN}"', f'"{bash}"', "-c", shlex.quote(" " + command)])


def wrap_file(path: Path, plugin: str, pythonw: str, bash: str) -> int:
    """Wrap each command handler in one plugin file; return how many changed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    events = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(events, dict):
        return 0
    changed = 0
    for groups in events.values():
        for group in groups if isinstance(groups, list) else []:
            for handler in group.get("hooks", []) if isinstance(group, dict) else []:
                command = handler.get("command") if isinstance(handler, dict) else None
                if handler.get("type") != "command" or not isinstance(command, str) or "run_hidden.py" in command:
                    continue
                handler["command"] = wrap(command, pythonw, bash)
                handler.setdefault("statusMessage", f"{plugin} plugin hook")
                changed += 1
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def run() -> list[str]:
    if os.name != "nt":
        return []  # shortcut: only Windows opens console windows for hooks
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    # Git Bash first: a bare `bash` on PATH can be the WSL launcher in System32
    bash = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")
    if not pythonw.exists() or not bash:
        return []
    lines = []
    for pattern in PATTERNS:
        for path in sorted(CACHE.glob(pattern)):
            changed = wrap_file(path, path.parts[len(CACHE.parts) + 1], pythonw.as_posix(), Path(bash).as_posix())
            if changed:
                lines.append(f"{path.relative_to(CACHE).as_posix()}: wrapped {changed} hook(s)")
    return lines


def log_run(started: float, record: dict) -> None:
    """Run log in .data/hide_plugin_windows/runs.jsonl; this file runs by path, so find core/ first."""
    try:
        sys.path.insert(0, str(ROOT))
        from core.py.runlog import log_run as write
        write("hide_plugin_windows", {"event": "SessionStart", **record}, started)
    except Exception:  # noqa: BLE001 - the log must never block the hook
        pass


def main() -> int:
    started, record = time.time(), {"outcome": "error"}
    try:
        try:  # the session id ties this run to a chat; a hand run has a tty and no payload
            sid = None if sys.stdin is None or sys.stdin.isatty() else json.load(sys.stdin).get("session_id")
        except (ValueError, OSError):
            sid = None
        lines = run()
        record = {"session_id": sid, "outcome": "wrapped" if lines else "nothing", "files": len(lines),
                  "note": "; ".join(lines)[:300]}
        if sys.stdout:  # pythonw has no stdout
            print(*lines, sep="\n")
    except Exception:  # noqa: BLE001 - a hook must never block the session
        pass
    log_run(started, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
