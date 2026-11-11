"""The JS core (core/js) must behave like the Python core (core/py): same log shape."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

JS = (Path(__file__).resolve().parents[1] / "core" / "js").as_posix()
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def _node(script: str, env=None) -> dict:
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True,
                         env={**os.environ, **(env or {})}).stdout
    return json.loads(out)


def test_log_matches_python_shape_and_rotates():
    from core.py import training_log

    with tempfile.TemporaryDirectory() as tmp:
        js_file, py_file = Path(tmp) / "js.jsonl", Path(tmp) / "py.jsonl"
        _node(f"const {{JsonlLog}}=require('{JS}/log');const l=new JsonlLog('{js_file.as_posix()}',50);"
              "l.append({a:'x'.repeat(60)});l.append({a:'y'});console.log('{}')")
        py = training_log.JsonlLog(str(py_file))
        with patch.object(training_log, "MAX_BYTES", 50):
            py.append({"a": "x" * 60})
            py.append({"a": "y"})
        for log in (js_file, py_file):
            assert len(Path(f"{log}.1").read_text(encoding="utf-8").splitlines()) == 1
            current = json.loads(log.read_text(encoding="utf-8"))
            assert list(current) == ["timestamp", "a"] and current["a"] == "y"
            assert isinstance(current["timestamp"], float)


def test_js_hooks_write_run_log_and_fail_open():
    root = Path(__file__).resolve().parents[1]
    log = root / ".data" / "noise_filter" / "runs.jsonl"
    before = log.read_text(encoding="utf-8").count("\n") if log.exists() else 0
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "pip install foo"}})
    hook = root / "hooks" / "noise_filter" / "noise-filter-pretooluse.js"
    r = subprocess.run([NODE, str(hook)], input=payload, capture_output=True, text=True)
    assert r.returncode == 0 and "updatedInput" in r.stdout
    last = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert last["outcome"] == "wrapped" and "duration_ms" in last
    assert log.read_text(encoding="utf-8").count("\n") == before + 1
