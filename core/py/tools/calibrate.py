"""Per-confidence follow rate of `use` decisions, to judge where the threshold should sit.

    python -m core.py.tools.calibrate [--since EPOCH_SECONDS]

Only `use` decisions can be followed (a `fallback` never asks Claude to act), so this can say whether
a higher threshold would drop mostly-ignored suggestions, not whether a lower one would add good ones.
"""
import sys

from ..training_log import JsonlLog, failure_log, followed_log, model_router_log, skill_router_log
from .watch_decisions import matching_decision

BUCKETS = [(60, 69), (70, 79), (80, 89), (90, 100)]
# Last decision logged under the old Laya threshold (25); the logs were relabelled "jev" afterwards,
# so provider cannot tell the eras apart.
JEV_ONLY_SINCE = 1793069483.11


def load(log_path: str, router: str) -> list[dict]:
    """Records of a log, including its rotated backup `<name>.1` (older records first)."""
    return [{**r, "router": router} for r in JsonlLog(log_path).read_all(with_backup=True)]


def report(router: str, decisions: list[dict], actions: list[dict], since: float):
    used = [d for d in decisions
            if d.get("decision") == "use" and d.get("session_id") and d.get("host") != "codex"
            and d["timestamp"] > since]
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


def percentile(sorted_values: list[int], pct: int) -> int:
    return sorted_values[min(len(sorted_values) - 1, len(sorted_values) * pct // 100)]


def latency(router: str, decisions: list[dict], failures: list[dict], since: float):
    times = sorted(d["elapsed_ms"] for d in decisions if "elapsed_ms" in d and d["timestamp"] > since)
    failed = sum(1 for f in failures if f.get("source") == router and f["timestamp"] > since)
    if not times:
        print(f"{router} latency: no timed decisions, {failed} failures")
        return
    print(f"{router} latency: n={len(times)} p50={percentile(times, 50)}ms p95={percentile(times, 95)}ms "
          f"max={times[-1]}ms, {failed} failures")


def main(argv: list[str]):
    since = float(argv[argv.index("--since") + 1]) if "--since" in argv else JEV_ONLY_SINCE
    actions = load(followed_log.path, "FOLLOW")
    model, skill = load(model_router_log.path, "MODEL"), load(skill_router_log.path, "SKILL")
    failures = load(failure_log.path, "FAIL")
    report("MODEL", model, actions, since)
    report("SKILL", skill, actions, since)
    print()
    latency("MODEL", model, failures, since)
    latency("SKILL", skill, failures, since)


if __name__ == "__main__":
    main(sys.argv[1:])
