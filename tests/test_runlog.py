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


@pytest.mark.parametrize("module,hook", [("hooks.model_router.hook", "model_router"),
                                         ("hooks.skill_router.hook", "skill_router")])
def test_router_hooks_log_error_on_bad_stdin(runs_dir, module, hook):
    import importlib
    with patch("sys.stdin", io.StringIO("not json")), patch("sys.stdout", io.StringIO()):
        with pytest.raises(SystemExit) as e:
            importlib.import_module(module).main()
    assert e.value.code == 0
    (record,) = _records(runs_dir, hook)
    assert record["event"] == "UserPromptSubmit" and record["outcome"] in ("error", "skipped", "disabled")


def test_router_hook_logs_decision(runs_dir):
    from core.py import provider
    from hooks.model_router import hook, state

    payload = json.dumps({"session_id": "s", "prompt": "write a long detailed report please"})
    with patch.object(state, "is_enabled", return_value=True), patch.object(state, "record_classification"), \
            patch.object(provider, "classify_size", return_value={"size": "large", "confidence": 80, "provider": "jev"}), \
            patch.object(provider, "get_threshold", return_value=60), \
            patch("core.py.training_log.model_router_log.append"), \
            patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", io.StringIO()):
        with pytest.raises(SystemExit):
            hook.main()
    (record,) = _records(runs_dir, "model_router")
    assert (record["outcome"], record["size"], record["confidence"]) == ("use", "large", 80)
    assert "input_text" not in record and "prompt" not in record


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
