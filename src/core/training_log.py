"""Append-only JSONL logger for real classifications, used later as raw
material for fine-tuning. Purely local — never sent anywhere."""
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRAINING_DIR = os.path.join(ROOT, "data", "training")


MAX_BYTES = 10 * 1024 * 1024


class JsonlLog:
    def __init__(self, filename: str):
        os.makedirs(TRAINING_DIR, exist_ok=True)
        self.path = os.path.join(TRAINING_DIR, filename)

    def _rotate(self):
        """Move a full log to `<name>.1`, replacing the previous backup (only one is kept)."""
        try:
            if os.path.getsize(self.path) > MAX_BYTES:
                os.replace(self.path, self.path + ".1")
        except OSError:
            pass  # missing file, or another hook holds it open (Windows): try again on the next append

    def append(self, record: dict):
        self._rotate()
        record = {"timestamp": time.time(), **record}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def read_all(self) -> list:
        if not os.path.exists(self.path):
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records


model_router_log = JsonlLog("model_router_log.jsonl")
skill_router_log = JsonlLog("skill_router_log.jsonl")
followed_log = JsonlLog("followed_log.jsonl")
failure_log = JsonlLog("failures_log.jsonl")
labeled_log = JsonlLog("labeled.jsonl")
