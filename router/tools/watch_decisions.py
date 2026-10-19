"""Live view of the routers' decisions: tails the model and skill training logs and prints one line per
classification, plus a line whenever the Laya server goes up or down.

    python -m router.tools.watch_decisions [--last N]

`dispatch` shows what CLAUDE.md tells Claude to do for a `use` decision. Whether Claude followed it is not logged.
"""
import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime

from ..core import config
from ..core.laya_server import HOST
from ..core.training_log import TRAINING_DIR

RESET, DIM, GREEN, YELLOW, CYAN, RED = "\033[0m", "\033[2m", "\033[32m", "\033[33m", "\033[36m", "\033[31m"
DISPATCH = {"tiny": "router-haiku", "everyday": "router-haiku", "large": "router-sonnet", "hardest": "router-sonnet"}
POLL_SECONDS = 0.3
SERVER_CHECK_SECONDS = 3


class LogTail:
    """New records of one JSONL file since the last poll (a shorter file is read again from the start)."""

    def __init__(self, filename: str, label: str):
        self.path = os.path.join(TRAINING_DIR, filename)
        self.label = label
        self.offset = 0
        self.partial = ""

    def poll(self) -> list[dict]:
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        if size < self.offset:
            self.offset, self.partial = 0, ""
        with open(self.path, "r", encoding="utf-8") as f:
            f.seek(self.offset)
            text = self.partial + f.read()
            self.offset = f.tell()
        *lines, self.partial = text.split("\n")
        records = []
        for line in lines:
            try:
                records.append({**json.loads(line), "router": self.label})
            except ValueError:
                continue
        return records

    def skip_to_last(self, count: int) -> list[dict]:
        """Move to the end of the file and return its last `count` records."""
        return self.poll()[-count:] if count > 0 else self._discard()

    def _discard(self) -> list[dict]:
        self.poll()
        return []


def format_record(record: dict, width: int) -> str:
    when = datetime.fromtimestamp(record["timestamp"]).strftime("%H:%M:%S")
    used = record["decision"] == "use"
    colour = GREEN if used else YELLOW
    threshold = config.get_confidence_threshold(record.get("provider", "laya"))
    if record["router"] == "MODEL":
        pick = record["predicted_size"]
        threshold = record.get("threshold", threshold)
        action = f"-> {DISPATCH.get(pick, '?')}" if used else "answer normally"
    else:
        pick = record["predicted_skill"]
        action = f"-> Skill({pick})" if used else "no suggestion"
    head = f"{DIM}{when}{RESET}  {CYAN}{record['router']:<5}{RESET}  {colour}{record['decision']:<8}{RESET}  {pick:<24.24}  {record['confidence']:>3}%/{threshold}%  {action}"
    visible = len(f"{when}  {record['router']:<5}  {record['decision']:<8}  {pick:<24.24}  {record['confidence']:>3}%/{threshold}%  {action}")
    room = max(width - visible - 4, 10)
    prompt = " ".join(record["input_text"].split())
    if len(prompt) > room:
        prompt = prompt[: room - 3] + "..."
    return f'{head}  {DIM}"{prompt}"{RESET}'


def server_up() -> bool:
    try:
        urllib.request.urlopen(f"http://{HOST}:{config.get_laya_server_port()}/health", timeout=0.5).close()
        return True
    except OSError:
        return False


def server_line(up: bool) -> str:
    when = datetime.now().strftime("%H:%M:%S")
    state = f"{GREEN}up{RESET}" if up else f"{RED}down{RESET}  {DIM}(the next prompt starts it; that prompt is skipped){RESET}"
    return f"{DIM}{when}{RESET}  {CYAN}SERVER{RESET}  laya {state}"


def main(argv: list[str]) -> int:
    last = int(argv[argv.index("--last") + 1]) if "--last" in argv else 5
    os.system("")  # enables ANSI colours in the Windows console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # prompts can hold characters the console code page lacks
    tails = [LogTail("model_router_log.jsonl", "MODEL"), LogTail("skill_router_log.jsonl", "SKILL")]
    print(f"Watching {TRAINING_DIR}  (Ctrl+C to stop)\n"
          f"{DIM}use = Claude is told to act on it, fallback = Claude answers normally{RESET}\n")
    backlog = sorted((r for t in tails for r in t.skip_to_last(last)), key=lambda r: r["timestamp"])
    state, next_check = None, 0.0
    try:
        while True:
            width = shutil.get_terminal_size((120, 20)).columns
            if time.time() >= next_check:
                up, next_check = server_up(), time.time() + SERVER_CHECK_SECONDS
                if up != state:
                    print(server_line(up), flush=True)
                    state = up
            fresh = backlog + sorted((r for t in tails for r in t.poll()), key=lambda r: r["timestamp"])
            backlog = []
            for record in fresh:
                print(format_record(record, width), flush=True)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
