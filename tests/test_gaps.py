"""Frontmatter parsing, picker threshold, hook fail-open, and the hidden launcher."""
import io
import sys
from unittest.mock import patch

import pytest


def test_parse_frontmatter_plain_quoted_and_block():
    from hooks.skill_router.catalog import parse_frontmatter
    text = '---\nname: pdf\ndescription: "Do PDFs"\n---\nbody'
    assert parse_frontmatter(text) == {"name": "pdf", "description": "Do PDFs"}
    block = "---\nname: x\ndescription: >\n  first line\n  second line\n---\n"
    assert parse_frontmatter(block)["description"] == "first line second line"
    assert parse_frontmatter("no header") == {}
    assert parse_frontmatter("") == {}


def test_picker_threshold_and_none():
    from hooks.skill_router.picker import SkillPicker
    from hooks.skill_router import picker as pm
    p = SkillPicker(skills=[("loop", "d")], threshold=70)
    for skill, conf, want in [("loop", 70, "use"), ("loop", 69, "fallback"), ("none", 99, "fallback")]:
        with patch.object(pm._provider, "pick_skill",
                          return_value={"skill": skill, "confidence": conf, "provider": "jev"}):
            assert p.choose("x")["decision"] == want


@pytest.mark.parametrize("module", ["hooks.skill_router.hook"])
def test_hooks_fail_open_on_bad_stdin(module):
    import importlib
    hook = importlib.import_module(module)
    out = io.StringIO()
    with patch("sys.stdin", io.StringIO("not json")), patch("sys.stdout", out):
        with pytest.raises(SystemExit) as e:
            hook.main()
    assert e.value.code == 0
    assert out.getvalue() == ""


def test_run_hidden_relays_stdin_stdout_and_exit_code():
    import subprocess
    from core.py import paths
    script = f"{paths.ROOT}/core/py/run_hidden.py"
    r = subprocess.run([sys.executable, script, sys.executable, "-c",
                        "import sys; print(sys.stdin.read().upper()); sys.exit(3)"],
                       input="abc", capture_output=True, text=True)
    assert r.stdout.strip() == "ABC"
    assert r.returncode == 3


def test_manage_hooks_add_remove_roundtrip(tmp_path):
    from core.py.tools import manage_hooks
    target = str(tmp_path / "settings.json")
    manage_hooks.add(target)
    manage_hooks.add(target)  # idempotent
    import json
    hooks = json.load(open(target))["hooks"]
    assert len(hooks["UserPromptSubmit"][0]["hooks"]) == 1
    assert hooks["UserPromptSubmit"][0]["hooks"][0]["command"] == manage_hooks.PYTHON_EXE
    manage_hooks.remove(target)
    assert "hooks" not in json.load(open(target))


def test_privacy_folders_patterns_and_project_overrides(tmp_path):
    import json
    from core.py import privacy
    work, other = tmp_path / "work", tmp_path / "other"
    (work / "sub").mkdir(parents=True)
    (other / ".claude").mkdir(parents=True)
    glob = tmp_path / "global.json"
    glob.write_text(json.dumps({"folders": [str(work)], "patterns": ["acme"]}))
    proj = other / ".claude" / "hooks-privacy.json"
    with patch.object(privacy, "GLOBAL_FILE", str(glob)):
        assert privacy.is_private("hello there", str(work / "sub"))       # folder rule, nested
        assert not privacy.is_private("hello there", str(other))           # outside
        assert privacy.is_private("about Acme budget", str(other))         # global pattern
        proj.write_text(json.dumps({"private": True}))
        assert privacy.is_private("hello there", str(other))               # project opts in
        proj.write_text(json.dumps({"inherit": False}))
        assert not privacy.is_private("about Acme budget", str(other))     # project drops global
        proj.write_text(json.dumps({"patterns": ["zeta"]}))
        assert privacy.is_private("zeta plan", str(other))                 # project pattern adds
        assert privacy.is_private("about Acme", str(other))                # ...and inherits global
        (work / ".claude").mkdir()
        (work / ".claude" / "hooks-privacy.json").write_text(json.dumps({"private": False}))
        assert not privacy.is_private("hello there", str(work))            # project overrides folder rule
        assert privacy.is_private("my password is x", str(work))           # built-in secrets still win
        proj.write_text("{broken")
        assert privacy.is_private("hello there", str(other))               # unreadable file fails closed
