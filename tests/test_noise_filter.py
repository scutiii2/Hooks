"""noise_filter: which commands get wrapped, and how the filter trims. Runs a copy under tmp, so the real log stays clean."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def root(tmp_path):
    shutil.copytree(REPO / "core" / "js", tmp_path / "core" / "js")
    shutil.copytree(REPO / "hooks" / "noise_filter", tmp_path / "hooks" / "noise_filter")
    return tmp_path


def wrapped(root, command):
    hook = root / "hooks" / "noise_filter" / "noise-filter-pretooluse.js"
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    r = subprocess.run([NODE, str(hook)], input=payload, capture_output=True, text=True, check=True)
    return "updatedInput" in r.stdout


def last_log(root):
    lines = (root / ".data" / "noise_filter" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    return json.loads(lines[-1])


@pytest.mark.parametrize("command", ["pip install foo", "npm install", "pytest", "npm test", "python -m pytest",
                                     "cargo test", "docker build ."])
def test_noisy_commands_are_wrapped(root, command):
    assert wrapped(root, command)


@pytest.mark.parametrize("command", ["pytest -q", "pytest tests/test_x.py", "pytest tests/a.py::t", "npm run dev",
                                     "make all", "cat jest.config.js", "pip install x | tail -3",
                                     "npm install > out.txt", "git commit -m 'pip install'", "ls"])
def test_short_or_unrelated_commands_are_left_alone(root, command):
    assert not wrapped(root, command)


def test_log_keeps_program_and_subcommand_only(root):
    wrapped(root, "pip install secret-token-123")
    assert last_log(root)["command"] == "pip install"


def run_filter(root, text, code=None):
    script = root / "hooks" / "noise_filter" / "noise-filter.js"
    args = [NODE, str(script)]
    if code is not None:
        ec = root / "ec"
        ec.write_text(f"{code}\n")
        args += [str(ec), "pip install"]
    return subprocess.run(args, input=text, capture_output=True, text=True, check=True).stdout


def test_short_output_passes_through(root):
    text = "".join(f"line {i}\n" for i in range(80))
    assert run_filter(root, text) == text
    assert last_log(root)["outcome"] == "passthrough"


def test_long_output_keeps_error_with_context_and_tail(root):
    lines = [f"line {i}" for i in range(300)]
    lines[100] = "ERROR: boom"
    out = run_filter(root, "\n".join(lines) + "\n", code=0)
    assert "line 98" in out and "ERROR: boom" in out and "line 102" in out and "line 103" not in out
    assert "line 299" in out and "line 274" not in out and "line 275" in out
    rec = last_log(root)
    assert rec["outcome"] == "trimmed" and rec["exit_code"] == 0 and rec["command"] == "pip install"
    assert "command_ms" in rec and "filter_ms" in rec and rec["bytes_out"] < rec["bytes_in"]


def test_failed_run_under_200_lines_is_kept_whole(root):
    text = "".join(f"line {i}\n" for i in range(150))
    assert run_filter(root, text, code=1) == text
    assert last_log(root)["exit_code"] == 1


def test_failed_run_over_200_lines_is_trimmed(root):
    text = "".join(f"line {i}\n" for i in range(300))
    assert "[noise-filter] kept" in run_filter(root, text, code=1)


def test_warning_lines_keep_no_context(root):
    lines = [f"line {i}" for i in range(300)]
    lines[100] = "npm warn deprecated foo"
    out = run_filter(root, "\n".join(lines) + "\n")
    assert "deprecated" in out and "line 99" not in out and "line 101" not in out
