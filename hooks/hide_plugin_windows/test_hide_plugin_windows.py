"""Self-check for hide_plugin_windows.py. Run: py -m pytest hooks/hide_plugin_windows"""
import json
import os
import subprocess
import sys

import hide_plugin_windows as h


def test_wrap_file_wraps_once_and_keeps_command_runnable(tmp_path):
    f = tmp_path / "hooks.json"
    cmd = 'HOOK_ROOT=$(echo "$X"); node "it\'s/a.js"'
    f.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": cmd}]}]}}))
    assert h.wrap_file(f, "demo", "pw.exe", "bash.exe") == 1
    assert h.wrap_file(f, "demo", "pw.exe", "bash.exe") == 0  # idempotent
    handler = json.loads(f.read_text())["hooks"]["SessionStart"][0]["hooks"][0]
    assert handler["statusMessage"] == "demo plugin hook"
    # the wrapped string must round-trip to the original command through shell quoting
    import shlex
    assert shlex.split(handler["command"])[-1].strip() == cmd


def test_wrap_file_ignores_other_shapes(tmp_path):
    f = tmp_path / "cursor.json"
    f.write_text(json.dumps({"hooks": {"sessionStart": [{"command": "x"}]}}))
    assert h.wrap_file(f, "demo", "pw.exe", "bash.exe") == 0


def test_hidden_launcher_runs_wrapped_command(tmp_path):
    cmd = h.wrap('"$X/run" || echo hi', sys.executable.replace("\\", "/"), "bash")  # starts with a quote, like te-hook
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env={**os.environ, "X": "/nope"})
    assert out.stdout.strip() == "hi"
