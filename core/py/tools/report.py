"""Per-hook numbers from .data/<hook>/runs.jsonl, over two periods side by side.

    python -m core.py.tools.report                       all time, and the last 7 days
    python -m core.py.tools.report --days 30             all time, and the last 30 days
    python -m core.py.tools.report --split 2026-11-03    before / since that date (a change or tuning)
    python -m core.py.tools.report --hook skill_router   one hook
    python -m core.py.tools.report --skills              which suggested skills get ignored (raise their floors)

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


def followed_split(records: list[dict], actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """(followed, ignored) among `use` decisions with a session (Codex has no Skill call to match)."""
    used = [{**d, "router": "SKILL"} for d in records
            if d.get("decision") == "use" and d.get("session_id") and d.get("host") != "codex"]
    pending, followed = list(used), []
    for action in sorted(actions, key=lambda a: a["timestamp"]):
        match = matching_decision(action, pending)
        if match is not None:
            pending.remove(match)
            followed.append(match)
    return followed, pending


def follow_rate(records: list[dict], actions: list[dict]) -> str:
    followed, ignored = followed_split(records, actions)
    total = len(followed) + len(ignored)
    return f"followed {len(followed)}/{total} ({100 * len(followed) // total}%)" if total else "followed -"


def skill_table(records: list[dict], actions: list[dict], min_uses: int = 5) -> list[str]:
    """Skills suggested at least `min_uses` times, least followed first."""
    followed, ignored = followed_split(records, actions)
    count = Counter(d.get("predicted_skill") for d in followed + ignored)
    won = Counter(d.get("predicted_skill") for d in followed)
    rows = sorted(((won[s] / n, s, n) for s, n in count.items() if n >= min_uses), key=lambda r: (r[0], -r[2]))
    return [f"{s:<46} {won[s]:>3}/{n:<3} {round(100 * rate):>3}%" for rate, s, n in rows] or [f"no skill suggested {min_uses}+ times"]


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


GOOD = {"use", "followed", "injected", "output", "wrapped", "notes", "applied", "ok"}
BAD = {"failed", "error", "ignored?"}


def outcome_class(word) -> str:
    """'ok', 'warn' or 'bad' for a run outcome; anything that is not clearly good or bad is a skip."""
    word = str(word or "")
    return "bad" if word in BAD or word.startswith(("fail", "error")) else "ok" if word in GOOD else "warn"


def stats(days: int = 1, now: float | None = None) -> dict:
    """Numbers for the web Overview and Health pages: per hook over the last `days` (and the `days` before it), plus the follow rate."""
    now = time.time() if now is None else now
    start, before = now - days * DAY, now - 2 * days * DAY
    inside = lambda rows, a, b: [r for r in rows if a <= r.get("timestamp", 0) < b]
    decisions = load(data_path("skill_router", "decisions.jsonl"), "SKILL")
    actions = followed_log.read_all(with_backup=True)
    hooks, all_ms, prev_runs = [], [], 0
    for hook in sorted(os.listdir(DATA)) if os.path.isdir(DATA) else []:
        path = data_path(hook, "runs.jsonl")
        if not os.path.exists(path):
            continue
        runs = JsonlLog(path).read_all(with_backup=True)
        cur = inside(runs, start, now + 1)
        prev_runs += len(inside(runs, before, start))
        ms = [r["duration_ms"] for r in cur if isinstance(r.get("duration_ms"), (int, float))]
        all_ms += ms
        mix = Counter(outcome_class(r.get("outcome")) for r in cur)
        events = Counter(r.get("event") for r in runs[-200:] if r.get("event"))
        hooks.append({"name": hook, "event": events.most_common(1)[0][0] if events else "", "runs": len(cur),
                      "median_ms": round(sorted(ms)[len(ms) // 2]) if ms else 0, "p95_ms": p95(ms),
                      "ok": mix["ok"], "warn": mix["warn"], "bad": mix["bad"]})
    followed, ignored = followed_split(inside(decisions, start, now + 1), inside(actions, start, now + 1))
    total = len(followed) + len(ignored)
    worst = skill_table(inside(decisions, start, now + 1), inside(actions, start, now + 1))
    slow = max(hooks, key=lambda h: h["p95_ms"], default=None)
    return {"days": days, "hooks": hooks,
            "totals": {"runs": sum(h["runs"] for h in hooks), "prev_runs": prev_runs, "failed": sum(h["bad"] for h in hooks),
                       "median_ms": round(sorted(all_ms)[len(all_ms) // 2]) if all_ms else 0,
                       "slowest": {"name": slow["name"], "p95_ms": slow["p95_ms"]} if slow and slow["p95_ms"] else None},
            "follow": {"followed": len(followed), "total": total, "least": worst[0] if total and worst and "no skill" not in worst[0] else ""}}


def build(argv: list[str], now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    cols = periods(argv, now)
    only = argv[argv.index("--hook") + 1] if "--hook" in argv else None
    decisions = load(data_path("skill_router", "decisions.jsonl"), "SKILL")
    actions = followed_log.read_all(with_backup=True)
    lines = []
    if "--skills" in argv:
        for label, start, end in cols:
            lines.append(f"skills suggested, {label} (followed/suggested):")
            lines.extend("  " + x for x in skill_table([r for r in decisions if start <= r.get("timestamp", 0) < end],
                                                      [r for r in actions if start <= r.get("timestamp", 0) < end]))
        return lines
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
