"""Live view of the routers' decisions: tails the model and skill training logs and prints one line per
classification, plus a line whenever the Laya server goes up or down.

    python -m router.tools.watch_decisions [--last N]

`dispatch` shows what CLAUDE.md tells Claude to do for a `use` decision.
FOLLOW lines compare tool actions with the latest applicable suggestion in that session.
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
IGNORE_AFTER_SECONDS = 90


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


def matching_decision(action: dict, decisions: list[dict]) -> dict | None:
    session = action.get("session_id")
    if not session:
        return None
    tool = action.get("tool")
    if tool not in ("Skill", "Agent", "Task"):
        return None
    router = "SKILL" if tool == "Skill" else "MODEL"
    candidates = [r for r in decisions
                  if r.get("router") == router and r.get("decision") == "use"
                  and r.get("session_id") == session
                  and 0 <= action["timestamp"] - r["timestamp"] <= 300]
    if not candidates:
        return None
    latest = max(candidates, key=lambda r: r["timestamp"])
    target = latest.get("predicted_skill") if tool == "Skill" else DISPATCH.get(latest.get("predicted_size"))
    return latest if action.get("target") == target else None


def is_followed(action: dict, decisions: list[dict]) -> bool:
    return matching_decision(action, decisions) is not None


class PendingDecisions:
    """Live suggestions waiting for an action; no I/O or sleeping."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.decisions = []

    def add(self, decision: dict):
        if decision.get("session_id") and decision.get("decision") == "use":
            self.decisions.append(decision)

    def resolve(self, action: dict):
        matched = matching_decision(action, self.decisions)
        if matched is not None:
            self.decisions.remove(matched)

    def expired(self, now=None) -> list[dict]:
        now = self.clock() if now is None else now
        expired = [r for r in self.decisions if now - r["timestamp"] >= IGNORE_AFTER_SECONDS]
        self.decisions = [r for r in self.decisions if now - r["timestamp"] < IGNORE_AFTER_SECONDS]
        return expired


def with_prompt(head: str, record: dict, room: int) -> str:
    room = max(room, 10)
    prompt = " ".join(record["input_text"].split())
    if len(prompt) > room:
        prompt = prompt[: room - 3] + "..."
    return f'{head}  {DIM}"{prompt}"{RESET}'


def format_ignored(record: dict, width: int) -> str:
    when = datetime.now().strftime("%H:%M:%S")
    if record["router"] == "MODEL":
        pick = record["predicted_size"]
        target = DISPATCH.get(pick, "?")
    else:
        pick = record["predicted_skill"]
        target = f"Skill({pick})"
    detail = f"{record['router']} use {pick} -> {target}  no action in {IGNORE_AFTER_SECONDS}s"
    head = f"{DIM}{when}{RESET}  {CYAN}IGNORE{RESET}  {RED}ignored?{RESET}  {detail}"
    visible = len(f"{when}  IGNORE  ignored?  {detail}")
    return with_prompt(head, record, width - visible - 4)


def format_record(record: dict, width: int, decisions: list[dict] = ()) -> str:
    when = datetime.fromtimestamp(record["timestamp"]).strftime("%H:%M:%S")
    if record["router"] == "FOLLOW":
        followed = is_followed(record, decisions)
        colour, status = (GREEN, "followed") if followed else (YELLOW, "unprompted")
        return (f"{DIM}{when}{RESET}  {CYAN}FOLLOW{RESET}  {colour}{status}{RESET}  "
                f"{record['tool']}({record['target']})")
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
    return with_prompt(head, record, width - visible - 4)


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
    tails = [LogTail("model_router_log.jsonl", "MODEL"), LogTail("skill_router_log.jsonl", "SKILL"),
             LogTail("followed_log.jsonl", "FOLLOW")]
    print(f"Watching {TRAINING_DIR}  (Ctrl+C to stop)\n"
          f"{DIM}use = Claude is told to act on it, fallback = Claude answers normally{RESET}\n")
    # Seed matching with recent decisions even when --last hides them from display.
    initial = [t.poll() for t in tails]
    decisions = [r for records in initial for r in records if r["router"] != "FOLLOW"]
    backlog = sorted((r for records in initial for r in (records[-last:] if last > 0 else [])),
                     key=lambda r: r["timestamp"])
    state, next_check = None, 0.0
    pending, follow_off_notice = PendingDecisions(), False
    try:
        while True:
            width = shutil.get_terminal_size((120, 20)).columns
            follow_enabled = os.path.exists(tails[2].path)
            if time.time() >= next_check:
                up, next_check = server_up(), time.time() + SERVER_CHECK_SECONDS
                if up != state:
                    print(server_line(up), flush=True)
                    state = up
            fresh = sorted((r for t in tails for r in t.poll()), key=lambda r: r["timestamp"])
            decisions.extend(r for r in fresh if r["router"] != "FOLLOW")
            for record in backlog:
                print(format_record(record, width, decisions), flush=True)
            backlog = []
            for record in fresh:
                if record["router"] == "FOLLOW":
                    pending.resolve(record)
                elif record.get("session_id") and record.get("decision") == "use":
                    if follow_enabled:
                        pending.add(record)
                    elif not follow_off_notice:
                        print(f"{CYAN}FOLLOW{RESET}  {YELLOW}off{RESET}  followed hook not installed "
                              "(no followed_log.jsonl), ignored? disabled", flush=True)
                        follow_off_notice = True
                print(format_record(record, width, decisions), flush=True)
            if follow_enabled:
                for record in pending.expired():
                    print(format_ignored(record, width), flush=True)
            else:
                pending = PendingDecisions()  # An unobserved interval cannot prove an ignored suggestion.
            decisions = [r for r in decisions if r["timestamp"] >= time.time() - 300]
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
