"""One line per hook run in .data/<hook>/runs.jsonl: event, working folder, outcome, duration.
Same shape as core/js/runlog.js. Never raises: a broken log must not block a hook."""
import os
import time

from .paths import data_path
from .training_log import JsonlLog


def log_run(hook: str, record: dict, started: float):
    """`started` is a time.time() taken at the start of the run."""
    try:
        JsonlLog(data_path(hook, "runs.jsonl")).append({
            "hook": hook,
            "cwd": os.getcwd(),
            **record,
            "duration_ms": round((time.time() - started) * 1000),
        })
    except Exception:
        pass  # fail open
