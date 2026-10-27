"""Per-confidence follow rate of `use` decisions, to judge where the threshold should sit.

    python -m src.tools.calibrate

Only `use` decisions can be followed (a `fallback` never asks Claude to act), so this can say whether
a higher threshold would drop mostly-ignored suggestions, not whether a lower one would add good ones.
"""
import json
import os

from ..core.training_log import TRAINING_DIR
from .watch_decisions import matching_decision

BUCKETS = [(60, 69), (70, 79), (80, 89), (90, 100)]


def load(filename: str, router: str) -> list[dict]:
    path = os.path.join(TRAINING_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [{**json.loads(line), "router": router} for line in f if line.strip()]


def report(router: str, decisions: list[dict], actions: list[dict]):
    used = [d for d in decisions if d.get("decision") == "use" and d.get("session_id")]
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


def main():
    actions = load("followed_log.jsonl", "FOLLOW")
    report("MODEL", load("model_router_log.jsonl", "MODEL"), actions)
    report("SKILL", load("skill_router_log.jsonl", "SKILL"), actions)


if __name__ == "__main__":
    main()
