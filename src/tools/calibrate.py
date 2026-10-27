"""Per-confidence follow rate of `use` decisions, to judge where the threshold should sit.

    python -m src.tools.calibrate [--since EPOCH_SECONDS]

Only `use` decisions can be followed (a `fallback` never asks Claude to act), so this can say whether
a higher threshold would drop mostly-ignored suggestions, not whether a lower one would add good ones.
"""
import json
import os
import sys

from ..core.training_log import TRAINING_DIR
from .watch_decisions import matching_decision

BUCKETS = [(60, 69), (70, 79), (80, 89), (90, 100)]
# Last decision logged under the old Laya threshold (25); the logs were relabelled "jev" afterwards,
# so provider cannot tell the eras apart.
JEV_ONLY_SINCE = 1793069483.11


def load(filename: str, router: str) -> list[dict]:
    path = os.path.join(TRAINING_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [{**json.loads(line), "router": router} for line in f if line.strip()]


def report(router: str, decisions: list[dict], actions: list[dict], since: float):
    used = [d for d in decisions
            if d.get("decision") == "use" and d.get("session_id") and d["timestamp"] > since]
    print(f"\n{router}: {len(used)} use decisions with a session")
    for low, high in BUCKETS:
        rows = [d for d in used if low <= d["confidence"] <= high]
        # Same one-action-settles-one-decision rule as the watcher.
        pending, followed = list(rows), 0
        for action in sorted(actions, key=lambda a: a["timestamp"]):
            match = matching_decision(action, pending)
            if match is not None:
                pending.remove(match)
                followed += 1
        rate = f"{100 * followed // len(rows)}%" if rows else "-"
        print(f"  {low:>3}-{high:<3}%  n={len(rows):<4} followed={followed:<4} {rate}")


def main(argv: list[str]):
    since = float(argv[argv.index("--since") + 1]) if "--since" in argv else JEV_ONLY_SINCE
    actions = load("followed_log.jsonl", "FOLLOW")
    report("MODEL", load("model_router_log.jsonl", "MODEL"), actions, since)
    report("SKILL", load("skill_router_log.jsonl", "SKILL"), actions, since)


if __name__ == "__main__":
    main(sys.argv[1:])
