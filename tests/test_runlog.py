"""Every Python hook leaves one line in .data/<hook>/runs.jsonl and still fails open."""
import io
import json
import sys
import time
from unittest.mock import patch

import pytest

from core.py import runlog


def _records(runs_dir, hook):
    path = runs_dir / hook / "runs.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_log_run_shape_matches_js(runs_dir):
    runlog.log_run("h", {"event": "SessionStart", "outcome": "ok"}, time.time())
    (record,) = _records(runs_dir, "h")
    assert list(record) == ["timestamp", "hook", "cwd", "event", "outcome", "duration_ms"]


def test_log_run_never_raises():
    with patch.object(runlog, "JsonlLog", side_effect=OSError("disk full")):
        runlog.log_run("h", {"outcome": "ok"}, time.time())


@pytest.mark.parametrize("module,hook", [("hooks.skill_router.hook", "skill_router")])
def test_router_hooks_log_error_on_bad_stdin(runs_dir, module, hook):
    import importlib
    with patch("sys.stdin", io.StringIO("not json")), patch("sys.stdout", io.StringIO()):
        with pytest.raises(SystemExit) as e:
            importlib.import_module(module).main()
    assert e.value.code == 0
    (record,) = _records(runs_dir, hook)
    assert record["event"] == "UserPromptSubmit" and record["outcome"] in ("error", "skipped", "disabled")


def test_source_of_truth_logs_run(runs_dir, tmp_path):
    from hooks.source_of_truth import source_of_truth

    with patch.object(sys, "argv", ["x", str(tmp_path)]), patch("sys.stdin", io.StringIO("{}")):
        assert source_of_truth.main() == 0
    (record,) = _records(runs_dir, "source_of_truth")
    assert record["outcome"] in ("nothing", "output") and "duration_ms" in record


def test_te_patch_hook_logs_run(runs_dir):
    from hooks.token_economizer_patch import te_patch

    with patch.object(te_patch, "patches", return_value=[]):
        assert te_patch.hook() == 0
    (record,) = _records(runs_dir, "token_economizer_patch")
    assert record["event"] == "SessionStart" and record["outcome"] == "no_patch"


def test_te_patch_shows_a_repeated_note_once(runs_dir, tmp_path, capsys):
    from hooks.token_economizer_patch import te_patch

    note = ["Update conflicts with the history patch."]
    with patch.object(te_patch, "LAST_NOTE", tmp_path / "last_note.txt"), \
            patch.object(te_patch, "patches", return_value=["p"]), \
            patch.object(te_patch, "_needs_install", return_value=False), \
            patch.object(te_patch, "ensure", return_value=note):
        te_patch.hook()
        first = capsys.readouterr().out
        te_patch.hook()
        second = capsys.readouterr().out
    assert "Update conflicts" in first and second == ""
    assert [r["outcome"] for r in _records(runs_dir, "token_economizer_patch")] == ["notes", "repeat"]


def test_read_all_skips_torn_lines(tmp_path):
    from core.py.training_log import JsonlLog
    log = JsonlLog(str(tmp_path / "x.jsonl"))
    log.append({"a": 1})
    with open(log.path, "a", encoding="utf-8") as f:
        f.write('": 722}\n')  # tail left by two interleaved appends
    log.append({"a": 2})
    assert [r["a"] for r in log.read_all()] == [1, 2]
