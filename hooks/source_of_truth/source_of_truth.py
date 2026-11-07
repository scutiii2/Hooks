#!/usr/bin/env python3
"""SourceOfTruth: keep one copy of a project's agent rules and skills.

Runs as a Claude Code (or Codex) hook, on SessionStart and after file or shell
tool calls. For the project the session is in, it makes the single source of
truth `AGENTS.md` and `.agents/skills/`, and turns the Claude Code side into a
pointer to it:

- `.claude/skills/` is a real folder, `.agents/skills/` is missing:
  move it to `.agents/skills/` and leave a symlink `.claude/skills`.
- `.agents/skills/` exists, `.claude/skills` is missing: add the symlink.
- `CLAUDE.md` holds real rules, `AGENTS.md` is missing: move the rules to
  `AGENTS.md` and leave `CLAUDE.md` as `@AGENTS.md`.
- `AGENTS.md` exists, `CLAUDE.md` is missing: write `CLAUDE.md` as `@AGENTS.md`.
- Each skill folder in `.agents/skills/` gets a symlink in `~/.codex/skills/`, so Codex and Claude Code load the same
  skills from one copy. A real folder already there is left alone and reported.

It never overwrites or deletes content. When two real copies exist it leaves
both alone and says so (on SessionStart only). It creates nothing for a project
that has no rules or skills yet, and only acts inside the watched root (the
Programming workspace this file sits in). A hook must never block, so every
failure ends silently with exit code 0.

    py source_of_truth.py [PROJECT_DIR]    run by hand for one folder
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# shortcut: one watched root (Programming/), not configurable; add a config file when a second root appears.
ROOTS = [Path(__file__).resolve().parents[4]]
STUB = "@AGENTS.md"
LINK_TARGET = os.path.join("..", ".agents", "skills")


def project_dirs(cwd: Path, roots: list[Path]) -> list[Path]:
    """The session folder and its git root, when inside a watched root."""
    cwd = cwd.resolve()
    if not any(cwd.is_relative_to(r) for r in roots):
        return []
    root = next((p for p in (cwd, *cwd.parents) if (p / ".git").exists()), cwd)
    if not any(root.is_relative_to(r) for r in roots):
        root = cwd
    return list(dict.fromkeys([root, cwd]))


def unify_skills(project: Path) -> tuple[list[str], list[str]]:
    """Return (changes, warnings) after making .claude/skills a link to .agents/skills."""
    claude, agents = project / ".claude" / "skills", project / ".agents" / "skills"
    if claude.is_symlink():
        return [], []
    moved = False
    try:
        if claude.is_dir():
            if agents.exists() or agents.is_symlink():
                return [], [f"{project.name}: .claude/skills and .agents/skills are both real folders; merge by hand into .agents/skills."]
            agents.parent.mkdir(exist_ok=True)
            claude.rename(agents)
            moved = True
        elif not (agents.is_dir() and not agents.is_symlink()):
            return [], []
        claude.parent.mkdir(exist_ok=True)
        os.symlink(LINK_TARGET, claude, target_is_directory=True)
    except OSError as exc:
        if moved:
            agents.rename(claude)  # put the folder back; a half-done move would hide the skills
        return [], [f"{project.name}: cannot link .claude/skills ({exc}); on Windows turn on Developer Mode."]
    action = "moved .claude/skills to .agents/skills and linked it back" if moved else "linked .claude/skills to .agents/skills"
    return [f"{project.name}: {action}."], []


CODEX_SKILLS = Path.home() / ".codex" / "skills"


def link_codex_skills(project: Path, codex: Path | None = None) -> tuple[list[str], list[str]]:
    """Return (changes, warnings) after linking every skill of the project into ~/.codex/skills."""
    codex = CODEX_SKILLS if codex is None else codex
    agents = project / ".agents" / "skills"
    if not agents.is_dir() or not codex.is_dir():
        return [], []
    changes, warnings = [], []
    for skill in sorted(agents.iterdir()):
        if not (skill / "SKILL.md").is_file():
            continue
        target = codex / skill.name
        if target.is_symlink() or (target.exists() and os.path.samefile(target, skill)):
            continue  # a link or junction to this skill already
        if target.exists():
            warnings.append(f"{skill.name}: ~/.codex/skills has a real folder; delete it so the link can replace it.")
            continue
        try:
            os.symlink(skill.resolve(), target, target_is_directory=True)
            changes.append(f"linked ~/.codex/skills/{skill.name} to {project.name}/.agents/skills/{skill.name}.")
        except OSError as exc:
            warnings.append(f"{skill.name}: cannot link into ~/.codex/skills ({exc}); on Windows turn on Developer Mode.")
    return changes, warnings


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def unify_rules(project: Path) -> tuple[list[str], list[str]]:
    """Return (changes, warnings) after making CLAUDE.md a stub that imports AGENTS.md."""
    claude, agents = project / "CLAUDE.md", project / "AGENTS.md"
    if claude.is_symlink():
        return [], []
    try:
        text = claude.read_text(encoding="utf-8") if claude.is_file() else None
        if agents.is_file():
            if text is None:
                claude.write_text(STUB + "\n", encoding="utf-8")
                return [f"{project.name}: wrote CLAUDE.md importing AGENTS.md."], []
            if _norm(text) == STUB:
                return [], []
            if _norm(text) == _norm(agents.read_text(encoding="utf-8")):
                claude.write_text(STUB + "\n", encoding="utf-8")
                return [f"{project.name}: CLAUDE.md duplicated AGENTS.md; now imports it."], []
            return [], [f"{project.name}: CLAUDE.md and AGENTS.md differ; merge by hand into AGENTS.md."]
        if text and _norm(text) != STUB:
            agents.write_bytes(claude.read_bytes())
            claude.write_text(STUB + "\n", encoding="utf-8")
            return [f"{project.name}: moved CLAUDE.md rules to AGENTS.md; CLAUDE.md now imports it."], []
    except (OSError, UnicodeDecodeError) as exc:
        return [], [f"{project.name}: cannot unify rules ({exc})."]
    return [], []


def run(cwd: Path, event: str, roots: list[Path] = ROOTS) -> dict | None:
    """The hook output for this folder, or None when there is nothing to say."""
    lines: list[str] = []
    for project in project_dirs(cwd, roots):
        for step in (unify_skills, unify_rules, link_codex_skills):
            changes, warnings = step(project)
            lines += [f"SourceOfTruth: {c}" for c in changes]
            if event == "SessionStart":
                lines += [f"SourceOfTruth: {w}" for w in warnings]
    if not lines:
        return None
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": "\n".join(lines)}}


def log_run(started: float, record: dict) -> None:
    """Run log in .data/source_of_truth/runs.jsonl; this file runs by path, so find core/ first."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from core.py.runlog import log_run as write
        write("source_of_truth", record, started)
    except Exception:  # noqa: BLE001 - the log must never block the hook
        pass


def main() -> int:
    started, record = time.time(), {"outcome": "error"}
    try:
        data = {} if sys.stdin.isatty() else json.load(sys.stdin)
        cwd = Path(sys.argv[1] if len(sys.argv) > 1 else data.get("cwd") or os.getcwd())
        event = data.get("hook_event_name") or "SessionStart"
        output = run(cwd, event)
        record = {"event": event, "outcome": "output" if output else "nothing"}
        if output:
            print(json.dumps(output))
    except Exception:  # noqa: BLE001 - a hook must never block the session
        pass
    log_run(started, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
