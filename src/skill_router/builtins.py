"""Skills that have no SKILL.md on this machine, so catalog.py cannot discover them: Claude Code built-ins,
remote `anthropic-skills:*`, and plugin skills shipped without a file. Edit by hand.

The skill hook adds a [BUILTIN_SKILLS_CHECK] tag once a month (see due_notice); when Claude sees it, it
compares this list with its own skill list, fixes it and sets VERIFIED to today.
"""
import datetime
import os

from ..core.json_store import JsonStore
from ..core.paths import ROOT

VERIFIED = "2026-10-27"
CHECK_EVERY_DAYS = 30

BUILTINS = {
    'caveman:caveman-init': 'Drop the always-on caveman activation rule into the current repo for every IDE agent',
    'cowork-plugin-management:cowork-plugin-customizer': "Customize a Claude Code plugin for a specific organization's tools and workflows",
    'cowork-plugin-management:create-cowork-plugin': 'Guide users through creating a new plugin from scratch in a cowork session',
    'anthropic-skills:consolidate-memory': 'Reflective pass over memory files — merge duplicates, fix stale facts, prune the index',
    'anthropic-skills:docs': 'Create or edit a living shared doc (memo, spec, PRD, runbook) that people comment on and edit',
    'anthropic-skills:docx': 'Create, read, edit, or manipulate Word documents (.docx) or Word templates (.dotx)',
    'anthropic-skills:explain-usage': "Explain where this session's tokens went, with one simple chart in plain language",
    'anthropic-skills:import-memory': "Import a memory export from another AI assistant into Claude's memory",
    'anthropic-skills:morning': "Render or schedule the user's morning brief as a styled HTML artifact",
    'anthropic-skills:pdf': 'Read, extract, merge, split, rotate, watermark, fill, encrypt, or OCR PDF files',
    'anthropic-skills:pptx': 'Create, read, edit, or combine PowerPoint (.pptx/.potx) slide decks and templates',
    'anthropic-skills:setup-claude': 'Guided setup: install role-matched plugins, connect tools, try a skill',
    'anthropic-skills:setup-writing-style': "Learn the user's writing voice from their own sent messages/docs and save it as a profile",
    'anthropic-skills:skill-creator': 'Create, edit, optimize, or benchmark skills from scratch',
    'anthropic-skills:xlsx': 'Open, edit, create, or convert spreadsheets (.xlsx/.xlsm/.csv/.tsv)',
    'dataviz': 'Make a chart, graph, plot, dashboard, or any data visualization — bar/line/pie charts, trends by category or region',
    'artifact-design': 'Design guidance and fundamentals to load before writing any Artifact',
    'artifact-diagramming': 'Diagramming know-how for Artifacts: choosing and drawing clear inline-SVG diagrams',
    'artifact-capabilities': 'Runtime capabilities (live data, state, storage) an Artifact page can be granted',
    'update-config': 'Configure the Claude Code harness via settings.json: hooks, permissions, env vars',
    'keybindings-help': 'Customize keyboard shortcuts / rebind keys in ~/.claude/keybindings.json',
    'code-review': 'Review the current diff, a PR, branch, or path for correctness bugs and cleanups',
    'simplify': 'Review changed code for reuse/simplification/efficiency and apply the fixes',
    'fewer-permission-prompts': 'Scan transcripts for common read-only calls, add an allowlist to reduce prompts',
    'loop': 'Poll or check on something repeatedly on a recurring interval — e.g. check every N minutes if a deploy/build/job finished',
    'schedule': 'Create/update/list/run standing scheduled cloud agents on a cron schedule (long-lived automation, not a short one-off check-back)',
    'claude-api': 'Reference for the Claude API/Anthropic SDK: models, pricing, params, tool use, agents',
    'run': "Launch and drive this project's app to see a change working, screenshot it",
    'init': 'Initialize a new CLAUDE.md file with codebase documentation',
    'security-review': 'Complete a security review of the pending changes on the current branch',
    'anthropic-skills:built-in-browser': 'Use the browser pane inside the Claude desktop app: tabs, reading pages, site approvals',
    'anthropic-skills:chrome-browser': "Use Claude in Chrome, the extension that acts in the person's real Chrome with their sign-ins",
    'anthropic-skills:computer-use': "Control apps on the person's own computer through screenshots, clicks and typing",
    'anthropic-skills:deep-research': 'Research a topic across many sources and write a comprehensive narrative report',
    'anthropic-skills:google-workspace': "Create or change a Google Doc, Sheet or Slides file in the person's Drive",
    'plugin-authoring': "Make a mod: a panel, status line, toast, slash command or hook that changes Claude's own interface",
}


class _Reminded(JsonStore):
    path = os.path.join(ROOT, "data", "state", "builtins_reminded.json")
    defaults = {"date": ""}


def due_notice(today: datetime.date | None = None) -> str | None:
    """Tag asking Claude to re-verify BUILTINS. Once the check is overdue, at most once a day."""
    today = today or datetime.date.today()
    age = (today - datetime.date.fromisoformat(VERIFIED)).days
    reminded = _Reminded()
    if age < CHECK_EVERY_DAYS or reminded.read()["date"] == today.isoformat():
        return None
    reminded.write({"date": today.isoformat()})
    return (f"[BUILTIN_SKILLS_CHECK verified={VERIFIED} age={age}d] Once, when convenient: compare BUILTINS in "
            f"{os.path.abspath(__file__)} with the skills in your own available-skills list (built-in, remote and "
            f"plugin skills with no file on disk), fix any name or description that is wrong, add missing ones, "
            f"and set VERIFIED to {today.isoformat()}.")

