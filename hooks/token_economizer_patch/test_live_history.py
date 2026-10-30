"""Importing the sessions Claude Code saved before the plugin (plugin/history.py)."""
import json
import os
import time

import pytest

# Runs inside the upstream TokenEconomizer checkout (see README); skipped here, where it is not importable.
pytest.importorskip("tokeneconomizer")
from tokeneconomizer.plugin import history  # noqa: E402
from tokeneconomizer.plugin.cli import main as te  # noqa: E402
from tests.test_live_hooks import call, env, repo, store_for, trap_session  # noqa: E402,F401


def saved(home, repo, sid, i):
    """A session as Claude Code saved it: under projects/<slug>/, every entry carrying `cwd`,
    and old enough that no hook is still folding it."""
    d = home / "projects" / "slug"
    d.mkdir(parents=True, exist_ok=True)
    path = trap_session(str(d / f"{sid}.jsonl"), repo, i)
    rows = [json.loads(ln) for ln in open(path)]
    with open(path, "w") as fh:
        fh.write("\n".join(json.dumps(dict(r, cwd=repo)) for r in rows) + "\n")
    old = time.time() - 7200
    os.utime(path, (old, old))
    return path


def test_history_is_folded_once_marked_and_survives_corrupt_logs(env, repo, tmp_path):
    home = tmp_path / "claude"
    for i in range(3):
        saved(home, repo, f"h{i}", i)
    bad = home / "projects" / "slug" / "bad.jsonl"
    bad.write_bytes(b"\xff\xfe not json\n{")
    os.utime(bad, (time.time() - 7200,) * 2)
    (home / "projects" / "slug" / "h0" / "subagents").mkdir(parents=True)   # not a session
    root = env["TOKENECONOMIZER_HOME"]

    tally = history.ingest(root, env, str(home))
    assert tally == {"folded": 3, "empty": 1}
    st = store_for(env, repo)
    folded = st.read("folded.json")
    assert set(folded) == {"h0", "h1", "h2"} and all(v["historical"] for v in folded.values())
    assert all(r["historical"] for r in st.read_lines("ledger.jsonl"))
    assert st.read("untool.json")["sessions"] == 3          # the same stages as a live session
    assert st.read("envelope.json")["resolved_turns"] == [3, 3, 3]   # one turn of 3 calls each

    assert history.ingest(root, env, str(home)) == {}       # nothing changed: nothing read
    saved(home, repo, "h3", 3)
    assert history.ingest(root, env, str(home)) == {"folded": 1}
    assert len(st.read_lines("ledger.jsonl")) == 4

    # A session the hooks folded live is not learned from a second time.
    live = saved(home, repo, "live", 9)
    call(env, {"hook_event_name": "SessionStart", "session_id": "live", "cwd": repo,
               "transcript_path": live, "source": "startup"})
    call(env, {"hook_event_name": "SessionEnd", "session_id": "live", "cwd": repo,
               "transcript_path": live, "reason": "other"})
    assert history.ingest(root, env, str(home)) == {"already_folded": 1}
    assert len(st.read_lines("ledger.jsonl")) == 5


def test_no_history_folder_is_fine_and_the_command_imports(env, repo, tmp_path, monkeypatch):
    root = env["TOKENECONOMIZER_HOME"]
    assert history.ingest(root, env, str(tmp_path / "nope")) == {}
    home = tmp_path / "claude"
    saved(home, repo, "c0", 0)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("TE_CLAUDE_HISTORY_PATH", str(home))
    assert te(["--cwd", repo, "--host", "claude", "ingest-claude-history"]) == 0
    assert "c0" in store_for(env, repo).read("folded.json")


def test_the_first_start_launches_one_import(env, repo, tmp_path, monkeypatch):
    spawned = []
    from tokeneconomizer.plugin.context import LiveContext
    monkeypatch.setattr(LiveContext, "spawn", lambda self, argv, log: spawned.append(argv))
    env = dict(env)
    env.pop("TE_FOLD_SYNC")
    base = {"hook_event_name": "SessionStart", "cwd": repo, "source": "startup",
            "transcript_path": str(tmp_path / "t.jsonl")}
    first = call(env, dict(base, session_id="a"))
    call(env, dict(base, session_id="b"))
    assert [a for a in spawned if a[0] == "ingest-claude-history"] == [
        ["ingest-claude-history", "--quiet"]]
    assert "learning in the background" in first["systemMessage"]
