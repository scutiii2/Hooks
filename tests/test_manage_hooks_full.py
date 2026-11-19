"""`manage_hooks add` installs every hook of this folder, and counts a hook as installed however it is launched."""
import json

from core.py.tools import manage_hooks as m


def _scripts(path):
    return sorted(w.rsplit("/", 1)[-1] for v in json.loads(path.read_text())["hooks"].values()
                  for g in v for h in g["hooks"] for w in m.command_words(h) if w.endswith((".py", ".js")) and "run_hidden" not in w)


def test_fresh_claude_install_has_all_hooks_and_the_markdown_filter(tmp_path):
    path = tmp_path / "s.json"
    m.add(str(path), "claude")
    assert _scripts(path) == sorted(["noise-filter-pretooluse.js", "te_patch.py", "session_temp_cleanup.py", "coding-rules-inject.js",
                                     "source_of_truth.py", "hide_plugin_windows.py", "run_hook.py", "source_of_truth.py", "run_hook.py"])
    edit = next(g for g in json.loads(path.read_text())["hooks"]["PostToolUse"] if g["matcher"] == "Write|Edit|MultiEdit")
    assert edit["hooks"][0]["if"] == "Edit(**/*.md)"
    m.add(str(path), "claude")  # second run adds nothing
    assert len(_scripts(path)) == 9


def test_fresh_codex_install_also_cleans_temp_folders(tmp_path):
    path = tmp_path / "h.json"
    m.add(str(path), "codex")
    assert "session_temp_cleanup.py" in _scripts(path)


def test_hook_with_another_node_or_python_path_counts_as_installed(tmp_path):
    path = tmp_path / "s.json"
    other = {"type": "command", "timeout": 10, "command": '"C:/Py/pythonw.exe" "C:/x/run_hidden.py" "C:/Program Files/node/node.exe" '
             f'"{m.ROOT}/hooks/coding_rules/coding-rules-inject.js"'}
    path.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [other]}]}}))
    m.add(str(path), "claude")
    commands = [h["command"] for g in json.loads(path.read_text())["hooks"]["SessionStart"] for h in g["hooks"]]
    assert sum("coding-rules-inject.js" in c for c in commands) == 1
