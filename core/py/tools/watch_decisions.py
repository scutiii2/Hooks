"""Live view of the skill router's decisions: tails the skill training log and prints one line per
classification.

    python -m core.py.tools.watch_decisions [--last N]

FOLLOW lines compare tool actions with the latest applicable suggestion in that session.
"""
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime

from .. import config
from ..paths import DATA
from ..training_log import failure_log, followed_log, skill_router_log

RESET, DIM, GREEN, YELLOW, CYAN, RED = "\033[0m", "\033[2m", "\033[32m", "\033[33m", "\033[36m", "\033[31m"
ANSI = re.compile(r"\033\[[0-9;]*m")
POLL_SECONDS = 0.3
IGNORE_AFTER_SECONDS = 90


class LogTail:
    """New records of one JSONL file since the last poll (a shorter file is read again from the start)."""

    def __init__(self, path: str, label: str):
        self.path = path
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


def matching_decision(action: dict, decisions: list[dict]) -> dict | None:
    session = action.get("session_id")
    if not session:
        return None
    tool = action.get("tool")
    if tool != "Skill":
        return None
    candidates = [r for r in decisions
                  if r.get("router") == "SKILL" and r.get("decision") == "use"
                  and r.get("session_id") == session
                  and 0 <= action["timestamp"] - r["timestamp"] <= 300]
    # The oldest suggestion this action satisfies: one action settles one decision, so a newer unrelated
    # suggestion cannot hide it and make it expire as "ignored?".
    matches = [r for r in candidates
               if action.get("target") == r.get("predicted_skill")]
    return min(matches, key=lambda r: r["timestamp"]) if matches else None


def is_followed(action: dict, decisions: list[dict]) -> bool:
    return matching_decision(action, decisions) is not None


class PendingDecisions:
    """Live suggestions waiting for an action; no I/O or sleeping."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.decisions = []

    def add(self, decision: dict):
        # Codex has no Skill tool call to follow, so its suggestions can never be matched.
        if decision.get("session_id") and decision.get("decision") == "use" and decision.get("host") != "codex":
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


def with_prompt(head: str, record: dict, width: int) -> str:
    """Append the prompt, truncated to what is left of `width` after the (colour-coded) head."""
    room = max(width - len(ANSI.sub("", head)) - 4, 10)
    prompt = " ".join(record["input_text"].split())
    if len(prompt) > room:
        prompt = prompt[: room - 3] + "..."
    return f'{head}  {DIM}"{prompt}"{RESET}'


def format_ignored(record: dict, width: int) -> str:
    when = datetime.now().strftime("%H:%M:%S")
    pick = record["predicted_skill"]
    detail = f"{record['router']} {record.get('provider') or 'jev'} use {pick} -> Skill({pick})  no action in {IGNORE_AFTER_SECONDS}s"
    head = f"{DIM}{when}{RESET}  {CYAN}IGNORE{RESET}  {RED}ignored?{RESET}  {detail}"
    return with_prompt(head, record, width)


def format_record(record: dict, width: int, decisions: list[dict] = ()) -> str:
    when = datetime.fromtimestamp(record["timestamp"]).strftime("%H:%M:%S")
    if record["router"] == "FAIL":
        return (f"{DIM}{when}{RESET}  {CYAN}FAIL{RESET}   {RED}{record['source']:<5} {record['error'][:70]}{RESET}"
                f"  {record.get('elapsed_ms', '-')}ms")
    if record["router"] == "FOLLOW":
        followed = is_followed(record, decisions)
        colour, status = (GREEN, "followed") if followed else (YELLOW, "unprompted")
        return (f"{DIM}{when}{RESET}  {CYAN}FOLLOW{RESET}  {colour}{status}{RESET}  "
                f"{record['tool']}({record['target']})")
    used = record["decision"] == "use"
    colour = GREEN if used else YELLOW
    provider = record.get("provider") or "jev"  # older records carry no provider
    threshold = config.get_confidence_threshold("skill_router", provider)
    pick = record["predicted_skill"]
    action = f"-> Skill({pick})" if used else "no suggestion"
    elapsed = f"{record['elapsed_ms']}ms" if "elapsed_ms" in record else "-"  # older records carry no timing
    head = f"{DIM}{when}{RESET}  {CYAN}{record['router']:<5}{RESET}  {provider:<4}  {colour}{record['decision']:<8}{RESET}  {pick:<24.24}  {record['confidence']:>3}%/{threshold}%  {elapsed:>6}  {action}"
    return with_prompt(head, record, width)


def main(argv: list[str]) -> int:
    last = int(argv[argv.index("--last") + 1]) if "--last" in argv else 5
    os.system("")  # enables ANSI colours in the Windows console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # prompts can hold characters the console code page lacks
    tails = [LogTail(skill_router_log.path, "SKILL"),
             LogTail(followed_log.path, "FOLLOW"), LogTail(failure_log.path, "FAIL")]
    print(f"Watching {DATA}  (Ctrl+C to stop)\n"
          f"{DIM}use = Claude is told to act on it, fallback = Claude answers normally{RESET}\n")
    # Seed matching with recent decisions even when --last hides them from display.
    initial = [t.poll() for t in tails]
    decisions = [r for records in initial for r in records if r["router"] != "FOLLOW"]
    backlog = sorted((r for records in initial for r in (records[-last:] if last > 0 else [])),
                     key=lambda r: r["timestamp"])
    pending, follow_off_notice = PendingDecisions(), False
    try:
        while True:
            width = shutil.get_terminal_size((120, 20)).columns
            follow_enabled = os.path.exists(tails[1].path)
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
                              "(no followed.jsonl), ignored? disabled", flush=True)
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
