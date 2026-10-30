"""Append-only JSONL logger for real classifications and tool follow-ups, used later as raw
material for fine-tuning. Purely local — never sent anywhere.

Decisions and shared logs live in .data/<hook>/; reviewed examples in .memory/ (see paths.py)."""
import json
import os
import time

from .paths import data_path, memory_path

MAX_BYTES = 10 * 1024 * 1024


class JsonlLog:
    def __init__(self, path: str):
        self.path = path

    def _rotate(self):
        """Move a full log to `<name>.1`, replacing the previous backup (only one is kept)."""
        try:
            if os.path.getsize(self.path) > MAX_BYTES:
                os.replace(self.path, self.path + ".1")
        except OSError:
            pass  # missing file, or another hook holds it open (Windows): try again on the next append

    def append(self, record: dict):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._rotate()
        record = {"timestamp": time.time(), **record}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def read_all(self, with_backup: bool = False) -> list:
        """All records; with_backup also reads the rotated `<name>.1` first (older records first)."""
        records = []
        for path in ((self.path + ".1", self.path) if with_backup else (self.path,)):
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    records += [json.loads(line) for line in f if line.strip()]
        return records


skill_router_log = JsonlLog(data_path("skill_router", "decisions.jsonl"))
followed_log = JsonlLog(data_path("core", "followed.jsonl"))
failure_log = JsonlLog(data_path("core", "failures.jsonl"))
labeled_log = JsonlLog(memory_path("core", "labeled.jsonl"))
