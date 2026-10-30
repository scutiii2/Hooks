"""Offline assert-based tests; also runnable without pytest."""
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_followed_payloads():
    from core.py import training_log
    from core.py.tools import log_followed

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        path = Path(tmp) / "followed.jsonl"
        with patch.object(training_log.followed_log, "path", str(path)):
            for tool, field in [("Skill", "skill"), ("Agent", "subagent_type"), ("Task", "subagent_type")]:
                payload = {"session_id": "s1", "tool_name": tool,
                           "tool_input": {field: "loop", "prompt": "private text"}}
                with patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(io.StringIO()) as out:
                    log_followed.main()
                assert out.getvalue() == ""
            with patch("sys.stdin", io.StringIO('{"tool_name":"Skill","tool_input":{"skill":"loop"}}')):
                log_followed.main()
            for raw in ['bad json', 'null', '[]', '{}', '{"tool_name":"Skill","tool_input":null}',
                        '{"tool_name":"Skill","tool_input":{"skill":42}}',
                        '{"tool_name":"Bash","tool_input":{"skill":"loop"}}']:
                with patch("sys.stdin", io.StringIO(raw)):
                    log_followed.main()
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(records) == 4
        assert records[-1]["session_id"] is None
        assert [r["tool"] for r in records] == ["Skill", "Agent", "Task", "Skill"]
        for record in records:
            assert set(record) == {"timestamp", "session_id", "tool", "target"}
            assert record["target"] == "loop"
            assert isinstance(record["timestamp"], (float, int))
        # Write errors also fail open.
        with patch.object(training_log.followed_log, "path", tmp), patch("sys.stdin", io.StringIO(json.dumps(payload))):
            log_followed.main()


def test_manage_hooks_idempotence():
    from core.py.tools import manage_hooks

    other = {"type": "command", "command": "other", "args": []}
    original = {"keep": True, "hooks": {
        "UserPromptSubmit": [{"matcher": "*", "hooks": [other]}],
        "PostToolUse": [{"matcher": "Skill|Agent|Task", "hooks": [other]},
                        {"matcher": "Bash", "hooks": [other]}]}}
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp, contextlib.redirect_stdout(io.StringIO()):
        path = Path(tmp) / "settings.json"
        manage_hooks.remove(str(path))
        assert not path.exists()
        path.write_text(json.dumps(original))
        manage_hooks.add(str(path))
        added = json.loads(path.read_text())
        follow = added["hooks"]["PostToolUse"][0]["hooks"]
        assert follow == [other, {"type": "command", "command": manage_hooks.PYTHON_EXE,
                                  "args": [manage_hooks.RUN_HOOK, "core.py.tools.log_followed"], "timeout": 5}]
        assert len(added["hooks"]["UserPromptSubmit"][0]["hooks"]) == 3
        manage_hooks.add(str(path))
        assert json.loads(path.read_text()) == added
        manage_hooks.remove(str(path))
        assert json.loads(path.read_text()) == original
        manage_hooks.remove(str(path))
        assert json.loads(path.read_text()) == original
        path.write_text('{}')
        manage_hooks.add(str(path))
        manage_hooks.remove(str(path))
        assert json.loads(path.read_text()) == {}


def test_follow_matching():
    from core.py.tools.watch_decisions import is_followed, format_record, GREEN, YELLOW

    skill = {"router": "SKILL", "session_id": "s1", "timestamp": 1000,
             "decision": "use", "predicted_skill": "loop"}
    model = {"router": "MODEL", "session_id": "s1", "timestamp": 1001,
             "decision": "use", "predicted_size": "large"}
    action = {"router": "FOLLOW", "session_id": "s1", "timestamp": 1010,
              "tool": "Skill", "target": "loop"}
    decisions = [model, skill]  # Ordering must not matter.
    assert is_followed(action, decisions)
    assert is_followed({**action, "timestamp": 1300}, decisions)
    for changes in [{"target": "other"}, {"session_id": "s2"}, {"session_id": None},
                    {"timestamp": 1300.01}, {"timestamp": 999}]:
        assert not is_followed({**action, **changes}, decisions)
    assert not is_followed(action, [{**skill, "decision": "fallback"}])
    assert not is_followed({**action, "session_id": None}, [{**skill, "session_id": None}])
    # A newer, different suggestion does not hide the older one the action followed.
    assert is_followed(action, decisions + [{**skill, "timestamp": 1005, "predicted_skill": "other"}])
    assert not is_followed({**action, "target": "third"}, decisions + [{**skill, "timestamp": 1005, "predicted_skill": "other"}])
    assert is_followed(action, decisions + [{**skill, "timestamp": 1005, "decision": "fallback"}])
    for tool in ["Agent", "Task"]:
        assert is_followed({**action, "tool": tool, "target": "router-sonnet"}, decisions)
        assert is_followed({**action, "tool": tool, "target": "router-haiku"}, [{**model, "predicted_size": "tiny"}])
        assert not is_followed({**action, "tool": tool, "target": "loop"}, decisions)
    assert GREEN + "followed" in format_record(action, 120, decisions)
    assert YELLOW + "unprompted" in format_record({**action, "target": "other"}, 120, decisions)


def test_decision_hooks_session_ids():
    from core.py import training_log, provider
    from hooks.model_router import hook as model_hook, state as model_state
    from hooks.skill_router import hook as skill_hook, state as skill_state, picker

    # Replace only classifier calls and file paths; run real stats and JSONL writes.
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        for label, hook, state, log in [
            ("model", model_hook, model_state, training_log.model_router_log),
            ("skill", skill_hook, skill_state, training_log.skill_router_log),
        ]:
            path = Path(tmp) / f"{label}.jsonl"
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(state, "is_enabled", return_value=True))
                stack.enter_context(patch.object(state._stats, "path", str(Path(tmp) / f"{label}_stats.json")))
                Path(state._stats.path).write_text(json.dumps(state._stats.defaults))
                stack.enter_context(patch.object(log, "path", str(path)))
                stack.enter_context(patch.object(provider, "get_threshold", return_value=25))
                stack.enter_context(patch.object(provider, "classify_size", return_value={
                    "size": "large", "confidence": 90, "provider": "jev"}))
                stack.enter_context(patch.object(picker, "choose", return_value={
                    "skill": "loop", "decision": "use", "confidence": 90, "provider": "jev", "error": None}))
                for extra in [{"session_id": "s1"}, {}]:
                    payload = {"prompt": "write a full report comparing database designs", **extra}
                    with patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(io.StringIO()) as out:
                        try:
                            hook.main()
                        except SystemExit as exit:
                            assert exit.code == 0
                    assert json.loads(out.getvalue())["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
            records = [json.loads(line) for line in path.read_text().splitlines()]
            assert [r["session_id"] for r in records] == ["s1", None]


def test_legacy_stats():
    from hooks.model_router.state import RouterStats
    from hooks.skill_router.state import SkillRouterStats

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        model, skill = RouterStats(), SkillRouterStats()
        for name, store in [("model", model), ("skill", skill)]:
            store.path = str(Path(tmp) / f"{name}.json")
            Path(store.path).write_text(json.dumps({**store.defaults, "jev_cost_usd": 1.25}))
        model.record_classification("large")
        skill.record("use")
        assert model.read()["counts"]["large"] == 1
        assert model.read()["jev_calls"] == 1
        assert skill.read()["used"] == 1


def test_pending_followed_and_expiry():
    from core.py.tools.watch_decisions import PendingDecisions

    now = [1000]
    pending = PendingDecisions(clock=lambda: now[0])
    skill = {"router": "SKILL", "session_id": "s1", "timestamp": 1000,
             "decision": "use", "predicted_skill": "loop"}
    action = {"session_id": "s1", "timestamp": 1010, "tool": "Skill", "target": "loop"}
    pending.add(skill)
    pending.resolve(action)
    assert pending.expired(1091) == []

    pending.add(skill)
    now[0] = 1089.99
    assert pending.expired() == []
    now[0] = 1090
    assert pending.expired() == [skill]
    assert pending.expired(1200) == []


def test_pending_rejects_unmatched_actions_and_null_sessions():
    from core.py.tools.watch_decisions import PendingDecisions

    skill = {"router": "SKILL", "session_id": "s1", "timestamp": 1000,
             "decision": "use", "predicted_skill": "loop"}
    action = {"session_id": "s1", "timestamp": 1010, "tool": "Skill", "target": "loop"}
    for changes in [{"target": "other"}, {"session_id": "s2"}, {"timestamp": 1300.01},
                    {"timestamp": 999}, {"tool": "Agent"}]:
        pending = PendingDecisions()
        pending.add(skill)
        pending.resolve({**action, **changes})
        assert pending.expired(1400) == [skill]
    pending = PendingDecisions()
    for decision in [{**skill, "session_id": None}, {k: v for k, v in skill.items() if k != "session_id"},
                     {**skill, "decision": "fallback"}]:
        pending.add(decision)
    assert pending.expired(1400) == []


def test_pending_dispatch_and_older_decision():
    from core.py.tools.watch_decisions import PendingDecisions, is_followed

    model = {"router": "MODEL", "session_id": "s1", "timestamp": 1000,
             "decision": "use", "predicted_size": "large"}
    for tool in ["Agent", "Task"]:
        pending = PendingDecisions()
        pending.add(model)
        pending.resolve({"tool": tool, "target": "router-sonnet", "session_id": "s1", "timestamp": 1300})
        assert pending.expired(1400) == []
    old = {"router": "SKILL", "session_id": "s1", "timestamp": 1000,
           "decision": "use", "predicted_skill": "loop"}
    new = {**old, "timestamp": 1005, "predicted_skill": "other"}
    action = {"tool": "Skill", "target": "loop", "session_id": "s1", "timestamp": 1010}
    pending = PendingDecisions()
    pending.add(new)
    pending.add(old)
    pending.resolve(action)
    # The action satisfies the older suggestion; the newer unrelated one stays pending and expires.
    assert pending.expired(1100) == [new]
    # Expiry never changes normal late FOLLOW matching.
    assert is_followed(action, [old])
    assert is_followed(action, [old, new])

    # Two suggestions for the same target: one action settles only the oldest.
    twin = {**old, "timestamp": 1005}
    pending = PendingDecisions()
    pending.add(twin)
    pending.add(old)
    pending.resolve(action)
    assert pending.expired(1100) == [twin]


def test_ignored_format():
    from core.py.tools.watch_decisions import format_ignored, RED

    decision = {"router": "MODEL", "session_id": "s1", "timestamp": 1000,
                "decision": "use", "predicted_size": "large", "input_text": "long prompt " * 30}
    line = format_ignored(decision, 120)
    assert RED + "ignored?" in line
    assert "MODEL jev use large -> router-sonnet" in line
    assert "no action in 90s" in line
    assert '..."' in line
    skill = {**decision, "router": "SKILL", "predicted_skill": "loop"}
    assert "SKILL jev use loop -> Skill(loop)" in format_ignored(skill, 120)


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print(f"PASS {name}")
