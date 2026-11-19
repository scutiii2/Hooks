"""Per-hook numbers from .data/<hook>/runs.jsonl, over two periods side by side.

    python -m core.py.tools.report                       all time, and the last 7 days
    python -m core.py.tools.report --days 30             all time, and the last 30 days
    python -m core.py.tools.report --split 2026-11-03    before / since that date (a change or tuning)
    python -m core.py.tools.report --hook skill_router   one hook

Per hook and period: runs, outcomes, average and 95th-percentile duration. skill_router also gets its
follow rate, and noise_filter the share of output bytes it removed.
"""
import os
import sys
import time
from collections import Counter
from datetime import datetime

from ..paths import DATA, data_path
from ..training_log import JsonlLog, followed_log
from .calibrate import load
from .watch_decisions import matching_decision

DAY = 86400


def periods(argv: list[str], now: float) -> list[tuple[str, float, float]]:
    """(label, from, to) for each column."""
    if "--split" in argv:
        raw = argv[argv.index("--split") + 1]
        try:
            cut = float(raw) if raw.replace(".", "", 1).isdigit() else datetime.fromisoformat(raw).timestamp()
        except ValueError:
            raise SystemExit(f"--split wants a date like 2026-11-03 or epoch seconds, got {raw!r}")
        return [(f"before {raw}", 0, cut), (f"since {raw}", cut, now + 1)]
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 7
    return [("all time", 0, now + 1), (f"last {days}d", now - days * DAY, now + 1)]


def p95(values: list[float]) -> int:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]) if ordered else 0


def follow_rate(records: list[dict], actions: list[dict]) -> str:
    """Share of `use` decisions (with a session, not Codex) that a matching tool call followed."""
    used = [{**d, "router": "SKILL"} for d in records
            if d.get("decision") == "use" and d.get("session_id") and d.get("host") != "codex"]
    pending, followed = list(used), 0
    for action in sorted(actions, key=lambda a: a["timestamp"]):
        match = matching_decision(action, pending)
        if match is not None:
            pending.remove(match)
            followed += 1
    return f"followed {followed}/{len(used)} ({100 * followed // len(used)}%)" if used else "followed -"


def summarize(hook: str, runs: list[dict], decisions: list[dict], actions: list[dict]) -> list[str]:
    if not runs:
        return ["no runs"]
    ms = [r["duration_ms"] for r in runs if isinstance(r.get("duration_ms"), (int, float))]
    top = ", ".join(f"{k} {v}" for k, v in Counter(r.get("outcome") or r.get("event") or "?" for r in runs).most_common(3))
    out = [f"{len(runs)} runs, avg {round(sum(ms) / len(ms)) if ms else 0} ms, p95 {p95(ms)} ms | {top}"]
    if hook == "skill_router":
        out.append(follow_rate(decisions, actions))
    if hook == "noise_filter":
        done = [r for r in runs if r.get("bytes_in")]
        bytes_in = sum(r["bytes_in"] for r in done)
        if bytes_in:
            out.append(f"filtered {len(done)} outputs, removed {100 - 100 * sum(r.get('bytes_out', 0) for r in done) // bytes_in}% of bytes")
    return out


def build(argv: list[str], now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    cols = periods(argv, now)
    only = argv[argv.index("--hook") + 1] if "--hook" in argv else None
    decisions = load(data_path("skill_router", "decisions.jsonl"), "SKILL")
    actions = followed_log.read_all(with_backup=True)
    lines = []
    for hook in sorted(os.listdir(DATA)) if os.path.isdir(DATA) else []:
        path = data_path(hook, "runs.jsonl")
        if (only and hook != only) or not os.path.exists(path):
            continue
        runs = JsonlLog(path).read_all(with_backup=True)
        lines.append(hook)
        for label, start, end in cols:
            pick = lambda rows: [r for r in rows if start <= r.get("timestamp", 0) < end]
            first, *rest = summarize(hook, pick(runs), pick(decisions), pick(actions))
            lines.append(f"  {label:<18}{first}")
            lines.extend(f"  {'':<18}{x}" for x in rest)
    return lines or ["no run logs yet"]


if __name__ == "__main__":
    print("\n".join(build(sys.argv[1:])))
