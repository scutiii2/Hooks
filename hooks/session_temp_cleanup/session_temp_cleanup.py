#!/usr/bin/env python3
"""SessionTempCleanup: delete the temp folders of deleted chats, for Claude Code or Codex.

Claude Code keeps per-session scratch files in `%TEMP%/claude/<project>/<session-id>/`
(task output, scratchpad). Deleting a chat removes its transcript
`~/.claude/projects/<project>/<session-id>.jsonl` but leaves that folder behind,
and one runaway task output once grew to 20 GB. No hook event fires on chat
deletion, so this runs on SessionStart and removes every session folder that
has no transcript any more.

A folder is kept when:
- its session id has a transcript in any `~/.claude/projects/*/`, or belongs to a chat in the
  desktop app's store (`%APPDATA%/Claude/claude-code-sessions/*/*/local_*.json`; the temp
  folder id is the app's `cliSessionId`, which can differ from the transcript name);
- it is the current session (id from the hook JSON on stdin);
- it changed in the last `GRACE_HOURS` (a new session writes its transcript late).

Codex (`--host codex`) cleans only its own folder: `~/.codex/generated_images/<thread-id>/`
(375 MB, one folder per chat). A folder goes when its thread id is not in the `threads` table
of `~/.codex/state_5.sqlite` (or in the current session) and it is older than `GRACE_HOURS`.
It never touches Claude's folders, and the Claude mode never touches Codex's. Codex's other
temp files (`codex-artifact-session-*`, `codex-clipboard-*`) are not keyed by chat and are tiny.

Only folders named like a session UUID are touched. A hook must never block, so every
failure ends silently with exit code 0.

    py session_temp_cleanup.py [--host claude|codex] [--dry-run]
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

GRACE_HOURS = 24
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def known_sessions(projects: Path, app_sessions: Path | None = None) -> set[str] | None:
    """Session ids of live chats: a transcript, or an entry in the desktop app's session store."""
    ids = {f.stem for d in projects.glob("*") if d.is_dir() for f in d.glob("*.jsonl")}
    for f in (app_sessions.glob("*/*/local_*.json") if app_sessions else ()):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # unreadable store: unknown, so the caller must delete nothing
        ids |= {data.get("cliSessionId"), data.get("lastAssistantCliSessionId"),
                *(data.get("priorCliSessionIds") or [])}
    return ids


def newest_mtime(folder: Path) -> float:
    """Newest modification time inside a folder (the folder itself when empty)."""
    latest = folder.stat().st_mtime
    for root, dirs, files in os.walk(folder):
        for name in dirs + files:
            try:
                latest = max(latest, os.lstat(os.path.join(root, name)).st_mtime)
            except OSError:
                pass
    return latest


def sweep(temp_root: Path, projects: Path, current: str = "", dry_run: bool = False,
          now: float | None = None, app_sessions: Path | None = None) -> list[Path]:
    """Delete orphaned session folders under temp_root; return the ones removed."""
    now = time.time() if now is None else now
    known = known_sessions(projects, app_sessions)
    if known is None:
        return []
    keep = known | {current}
    removed: list[Path] = []
    for project in (p for p in temp_root.glob("*") if p.is_dir()):
        for session in (s for s in project.glob("*") if s.is_dir() and UUID.match(s.name)):
            if session.name in keep or now - newest_mtime(session) < GRACE_HOURS * 3600:
                continue
            if not dry_run:
                shutil.rmtree(session, ignore_errors=True)
            removed.append(session)
    return removed


def codex_threads(db: Path) -> set[str] | None:
    """Thread ids Codex still has; None when the database cannot be read or lists none."""
    try:
        with contextlib.closing(sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)) as con:
            ids = {row[0] for row in con.execute("select id from threads")}
    except sqlite3.Error:
        return None
    return ids or None  # an empty table means something is wrong, not that every chat is gone


def sweep_codex(images_root: Path, db: Path, current: str = "", dry_run: bool = False,
                now: float | None = None) -> list[Path]:
    """Delete generated-image folders of deleted Codex threads; return the ones removed."""
    now = time.time() if now is None else now
    threads = codex_threads(db)
    if threads is None:
        return []
    removed: list[Path] = []
    for folder in (f for f in images_root.glob("*") if f.is_dir() and UUID.match(f.name)):
        if folder.name in threads or folder.name == current or now - newest_mtime(folder) < GRACE_HOURS * 3600:
            continue
        if not dry_run:
            shutil.rmtree(folder, ignore_errors=True)
        removed.append(folder)
    return removed


def log_run(started: float, record: dict) -> None:
    """Run log in .data/session_temp_cleanup/runs.jsonl; this file runs by path, so find core/ first."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from core.py.runlog import log_run as write
        write("session_temp_cleanup", record, started)
    except Exception:  # noqa: BLE001 - the log must never block the hook
        pass


def main() -> int:
    started = time.time()
    try:
        # shortcut: reads stdin only when piped by a hook; a hand run has a tty and skips it.
        raw = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
        current = (json.loads(raw).get("session_id", "") if raw.strip() else "")
        dry = "--dry-run" in sys.argv
        if "codex" in sys.argv[sys.argv.index("--host") + 1:][:1] if "--host" in sys.argv else False:
            codex = Path.home() / ".codex"
            removed = sweep_codex(codex / "generated_images", codex / "state_5.sqlite", current, dry)
        else:
            removed = sweep(Path(tempfile.gettempdir()) / "claude", Path.home() / ".claude" / "projects",
                            current, dry_run=dry,
                            app_sessions=Path(os.environ["APPDATA"]) / "Claude" / "claude-code-sessions")
        if "--dry-run" in sys.argv:
            print("\n".join(map(str, removed)) or "nothing to delete")
        host = "codex" if "codex" in sys.argv else "claude"
        log_run(started, {"event": "SessionStart", "session_id": current, "host": host, "dry_run": dry,
                          "outcome": "removed" if removed else "nothing", "removed": len(removed)})
    except Exception:
        log_run(started, {"event": "SessionStart", "outcome": "error"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
