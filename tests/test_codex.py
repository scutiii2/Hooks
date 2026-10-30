"""Codex support: installer, skill catalog, suggestion tag, and the stats that skip Codex decisions."""
import io
import json
import sys
from unittest.mock import patch

import pytest

from core.py.tools import manage_hooks


def _commands(path, event):
    return [h["command"] for g in json.loads(path.read_text())["hooks"][event] for h in g["hooks"]]


def test_codex_install_is_idempotent_and_keeps_other_hooks(tmp_path, capsys):
    path = tmp_path / "hooks.json"
    other = {"type": "command", "command": "node theirs.js", "timeout": 30}
    original = {"hooks": {"SessionStart": [{"hooks": [other]}], "Stop": [{"hooks": [other]}]}}
    path.write_text(json.dumps(original))
    manage_hooks.add(str(path), "codex")
    added = json.loads(path.read_text())
    assert "/hooks" in capsys.readouterr().out  # Codex needs the user to trust the new hooks
    assert other in added["hooks"]["SessionStart"][0]["hooks"] and added["hooks"]["Stop"] == original["hooks"]["Stop"]
    assert sum("coding-rules-inject.js" in c for c in _commands(path, "SessionStart")) == 1
    assert any("hooks.skill_router.hook --host codex" in c for c in _commands(path, "UserPromptSubmit"))
    assert all("model_router" not in c and "log_followed" not in c and "noise" not in c
               for e in added["hooks"] for c in _commands(path, e))
    manage_hooks.add(str(path), "codex")
    assert json.loads(path.read_text()) == added
    manage_hooks.remove(str(path), "codex")
    assert json.loads(path.read_text()) == original


def test_codex_commands_are_plain_strings_without_args():
    for _, _, handlers in manage_hooks.GROUPS["codex"]:
        for h in handlers:
            assert "args" not in h and isinstance(h["command"], str) and h["timeout"]
    assert manage_hooks.main.__defaults__ == (None,)


def test_manage_hooks_cli_host_flag(tmp_path, capsys):
    path = tmp_path / "hooks.json"
    manage_hooks.main(["add", "--host", "codex", str(path)])
    assert path.exists() and "UserPromptSubmit" in json.loads(path.read_text())["hooks"]
    with pytest.raises(SystemExit):
        manage_hooks.main(["add", "--host", "nope", str(path)])


def test_codex_catalog_reads_agents_skills_and_plugin_cache(tmp_path, monkeypatch):
    from hooks.skill_router import catalog

    def skill(folder, name, desc):
        (folder / name).mkdir(parents=True)
        (folder / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n")

    home, project = tmp_path / "home", tmp_path / "project"
    skill(project / ".agents" / "skills", "proj-skill", "From the project.")
    skill(home / ".agents" / "skills", "user-skill", "From the user folder.")
    skill(tmp_path / "codex" / "plugins" / "cache" / "mkt" / "plug" / "1.0" / "skills", "plug-skill", "From a plugin.")
    skill(project / ".claude" / "skills", "claude-only", "Claude folder, not read for Codex.")
    monkeypatch.setattr(catalog, "CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)
    names = dict(catalog.load_skills("codex"))
    assert {"proj-skill", "user-skill", "plug-skill"} <= set(names) and "claude-only" not in names
    assert not set(dict(catalog.BUILTINS)) & set(names)  # Claude built-ins do not apply to Codex


def _run_skill_hook(argv, runs_dir):
    from core.py import training_log
    from hooks.skill_router import hook, picker, state

    payload = json.dumps({"session_id": "s", "prompt": "make a pdf out of these notes please"})
    out = io.StringIO()
    result = {"skill": "pdf", "confidence": 90, "decision": "use", "provider": "jev", "error": None}
    with patch.object(sys, "argv", ["hook", *argv]), patch.object(state, "is_enabled", return_value=True), \
            patch.object(state, "record"), \
            patch.object(picker.SkillPicker, "choose", return_value=result), \
            patch.object(picker, "choose", return_value=result), \
            patch("hooks.skill_router.catalog.load_skills", return_value=[("pdf", "Make PDFs")]), \
            patch.object(training_log.skill_router_log, "append") as append, \
            patch("hooks.skill_router.builtins.due_notice", return_value="[BUILTIN_SKILLS_CHECK]"), \
            patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", out):
        with pytest.raises(SystemExit):
            hook.main()
    return json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"], append.call_args[0][0]


def test_skill_hook_codex_tag_and_record(runs_dir):
    tag, record = _run_skill_hook(["--host", "codex"], runs_dir)
    assert tag.startswith("[SKILL_SUGGESTION skill=pdf confidence=90%]") and "$pdf" in tag
    assert "BUILTIN_SKILLS_CHECK" not in tag and record["host"] == "codex"
    logged = json.loads((runs_dir / "skill_router" / "runs.jsonl").read_text().splitlines()[-1])
    assert logged["host"] == "codex"


def test_skill_hook_claude_tag_is_unchanged(runs_dir):
    tag, record = _run_skill_hook([], runs_dir)
    assert tag.splitlines() == ["[BUILTIN_SKILLS_CHECK]", "[SKILL_SUGGESTION skill=pdf confidence=90%]"]
    assert "host" not in record


def test_codex_decisions_are_never_ignored_or_followed():
    import time
    from core.py.tools import web
    from core.py.tools.watch_decisions import PendingDecisions

    now = time.time()
    use = {"decision": "use", "session_id": "s", "predicted_skill": "pdf", "timestamp": now - 500}
    pending = PendingDecisions()
    pending.add({**use, "host": "codex"})
    pending.add(use)
    assert len(pending.decisions) == 1 and "host" not in pending.decisions[0]
    records = [{**use, "host": "codex"}, dict(use)]
    with patch.object(web, "tail", return_value=[]), patch("os.path.exists", return_value=True):
        web.add_status(records, "skill_router/decisions.jsonl")
    assert "status" not in records[0] and records[1]["status"] == "ignored?"
