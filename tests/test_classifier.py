"""Offline assert-based tests; also runnable without pytest."""
import io
import json
import os
import urllib.error
from unittest.mock import patch

CRITERIA = {"tiny": "a", "large": "b"}


def _call(body=None, error=None, key="k"):
    from core.py.classifiers import JevClassifier

    response = io.BytesIO(json.dumps(body).encode()) if body is not None else None
    opener = patch("urllib.request.urlopen", side_effect=error) if error else \
        patch("urllib.request.urlopen", return_value=response)
    with patch.dict(os.environ, {"TYPESAFE_API_KEY": key}), opener:
        return JevClassifier().ask_choice("msg", CRITERIA, 1.0)


def _fails(**kwargs) -> bool:
    from core.py.classifiers import ClassifierError

    try:
        _call(**kwargs)
    except ClassifierError:
        return True
    return False


def _answer(choice="tiny", confidence=0.8):
    return {"answers": {"answer": {"choice": choice, "confidence": confidence}}}


def test_jev_scales_confidence_to_percent():
    assert _call(_answer("large", 0.724)) == {"choice": "large", "confidence": 72}


def test_jev_rejects_bad_responses():
    assert _fails(body=_answer("huge"))  # option that was not offered
    assert _fails(body=_answer(confidence=1.5))
    assert _fails(body=_answer(confidence=True))
    assert _fails(body={"answers": {}})
    assert _fails(body=_answer(), key="")  # no API key


def test_jev_wraps_network_errors():
    assert _fails(error=urllib.error.URLError("down"))
    assert _fails(error=TimeoutError())
    assert _fails(error=urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"x")))


def test_classify_size_rejects_unknown_size():
    from core.py.classifiers import Classifier, ClassifierError

    class Fake(Classifier):
        def ask_choice(self, subject, criteria, timeout):
            return {"choice": "huge", "confidence": 90}

    try:
        Fake().classify_size("x")
    except ClassifierError:
        return
    raise AssertionError("unknown size accepted")


def test_config_precedence():
    from core.py import config

    with patch.dict(os.environ, {"CONFIDENCE_THRESHOLD": "42"}):
        assert config.get_confidence_threshold("model_router") == 42
    with patch.dict(os.environ, {"CONFIDENCE_THRESHOLD": ""}), \
            patch.object(config, "_read_config", return_value={"confidence_threshold": {"jev": 71}}):
        assert config.get_confidence_threshold("model_router") == 71
    with patch.dict(os.environ, {"CONFIDENCE_THRESHOLD": ""}), patch.object(config, "HOOKS", "missing"):
        assert config.get_confidence_threshold("model_router") == 60


def test_skill_picker_runs_batches_in_parallel():
    import threading
    import time
    from core.py.classifiers import ClassifierError
    from hooks.skill_router import picker as picker_module
    from hooks.skill_router.picker import SkillPicker

    skills = [(f"s{i}", "d") for i in range(6)]
    calls, lock = [], threading.Lock()

    def fake(request, batch, timeout):
        time.sleep(0.2)
        with lock:
            calls.append(len(batch))
        return {"skill": batch[0][0], "confidence": 80, "provider": "jev"}

    with patch.object(picker_module._provider, "pick_skill", side_effect=fake):
        started = time.perf_counter()
        result = SkillPicker(skills, batch_size=2).pick("x")
        elapsed = time.perf_counter() - started
    assert sorted(calls) == [2, 2, 2, 3]  # three batches, then the final round over the winners
    assert result["skill"] == "s0"
    assert elapsed < 0.55  # serial would be 0.8s

    def boom(request, batch, timeout):
        raise ClassifierError("down")

    with patch.object(picker_module._provider, "pick_skill", side_effect=boom):
        try:
            SkillPicker(skills, batch_size=2).pick("x")
        except ClassifierError:
            return
    raise AssertionError("batch error swallowed")


def test_jev_retries_once_on_429():
    from core.py.classifiers import JevClassifier

    def too_many():
        return urllib.error.HTTPError("u", 429, "slow down", {}, io.BytesIO(b"x"))

    ok = io.BytesIO(json.dumps(_answer()).encode())
    with patch.dict(os.environ, {"TYPESAFE_API_KEY": "k"}), patch.object(JevClassifier, "RETRY_DELAY", 0),             patch("urllib.request.urlopen", side_effect=[too_many(), ok]) as opened:
        assert JevClassifier().ask_choice("m", CRITERIA, 1.0)["choice"] == "tiny"
        assert opened.call_count == 2
    with patch.dict(os.environ, {"TYPESAFE_API_KEY": "k"}), patch.object(JevClassifier, "RETRY_DELAY", 0),             patch("urllib.request.urlopen", side_effect=[too_many(), too_many()]) as opened:
        assert _fails_with(opened) and opened.call_count == 2  # a second 429 is not retried again


def _fails_with(_opened) -> bool:
    from core.py.classifiers import ClassifierError, JevClassifier

    try:
        JevClassifier().ask_choice("m", CRITERIA, 1.0)
    except ClassifierError:
        return True
    return False


def test_hook_logs_failures():
    import contextlib
    import tempfile
    from pathlib import Path
    from core.py import provider, training_log
    from core.py.classifiers import ClassifierError
    from hooks.model_router import hook, state

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        path = Path(tmp) / "failures.jsonl"
        payload = json.dumps({"session_id": "s", "prompt": "write a long detailed report please"})
        with patch.object(training_log.failure_log, "path", str(path)),                 patch.object(state, "is_enabled", return_value=True),                 patch.object(state, "record_jev_failure"),                 patch.object(provider, "classify_size", side_effect=ClassifierError("HTTP 503: down")),                 patch("sys.stdin", io.StringIO(payload)), contextlib.suppress(SystemExit):
            hook.main()
        record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["source"] == "MODEL" and record["error"] == "HTTP 503: down" and "elapsed_ms" in record


def test_privacy_filter():
    from core.py.privacy import is_private

    for text in ["fix my .env file", "the API key leaked", "my password is x", "rotate the ssh key",
                 "export OPENAI=sk-abcdef123456", "use the access token", "Secret handling"]:
        assert is_private(text), text
    for text in ["token Zk3pQ9vLx2Rt7WmN4bYc8DfH1", "-----BEGIN RSA PRIVATE KEY-----", "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
                 "AKIAIOSFODNN7EXAMPLE", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc"]:
        assert is_private(text), text
    for text in ["count the tokens in this prompt", "sort a dict by key", "write the readme", "environment setup",
                 "commit 6329379c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f60", "see get_confidence_threshold_for_provider_name",
                 "PromptSubmitHookAdditionalContextHandler", r"D:\User\Documents\Programming\AI\Hooks\ClaudeRouters\src",
                 "https://api.typesafe.ai/v1/systemone-request-handler-v2"]:
        assert not is_private(text), text


def _run_hook(hook, prompt, log, patches) -> str:
    import contextlib
    import tempfile
    from pathlib import Path

    payload = json.dumps({"session_id": "s", "prompt": prompt})
    out = io.StringIO()
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        path = Path(tmp) / "log.jsonl"
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(log, "path", str(path)))
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(patch("sys.stdin", io.StringIO(payload)))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.suppress(SystemExit))
            hook.main()
        _run_hook.record = json.loads(path.read_text(encoding="utf-8").splitlines()[0]) if path.exists() else None
    return out.getvalue()


def test_model_hook_injects_tag_and_logs():
    from core.py import provider, training_log
    from hooks.model_router import hook, state

    result = {"size": "large", "confidence": 80, "provider": "jev"}
    for threshold, decision in ((60, "use"), (90, "fallback")):
        out = _run_hook(hook, "write a long detailed report please", training_log.model_router_log, [
            patch.object(state, "is_enabled", return_value=True),
            patch.object(state, "record_classification"),
            patch.object(provider, "classify_size", return_value=result),
            patch.object(provider, "get_threshold", return_value=threshold)])
        tag = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert tag == f"[ROUTER size=large confidence=80% threshold={threshold}% decision={decision}]"
        assert _run_hook.record["decision"] == decision and "elapsed_ms" in _run_hook.record


def test_skill_hook_injects_tag_skips_and_counts():
    from core.py import training_log
    from hooks.skill_router import builtins, hook, picker, state

    result = {"skill": "pdf", "confidence": 75, "decision": "use", "provider": "jev", "error": None}
    no_notice = patch.object(builtins, "due_notice", return_value=None)
    prompt = "make a pdf out of these notes please"
    out = _run_hook(hook, prompt, training_log.skill_router_log, [
        patch.object(state, "is_enabled", return_value=True),
        patch.object(state, "record"), no_notice,
        patch.object(picker, "choose", return_value=result)])
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == "[SKILL_SUGGESTION skill=pdf confidence=75%]"
    assert _run_hook.record["predicted_skill"] == "pdf" and "elapsed_ms" in _run_hook.record

    with patch.object(state, "record_skipped") as skipped:
        out = _run_hook(hook, "fix my .env file", training_log.skill_router_log, [
            patch.object(state, "is_enabled", return_value=True), no_notice,
            patch.object(picker, "choose", side_effect=AssertionError("private prompt was classified"))])
    assert out == "" and skipped.call_count == 1

    notice = "[BUILTIN_SKILLS_CHECK verified=x age=40d] check"
    out = _run_hook(hook, "make a pdf out of these notes please", training_log.skill_router_log, [
        patch.object(state, "is_enabled", return_value=True), patch.object(state, "record"),
        patch.object(builtins, "due_notice", return_value=notice),
        patch.object(picker, "choose", return_value=result)])
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == (
        notice + chr(10) + "[SKILL_SUGGESTION skill=pdf confidence=75%]")


def test_env_layers():
    import tempfile
    from pathlib import Path
    from core.py import env_load

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        root = Path(tmp)
        (root / "h").mkdir()
        (root / ".env").write_text("A=root" + chr(10) + "B=root" + chr(10) + "C=root", encoding="utf-8")
        (root / "h" / ".env").write_text("B=hook" + chr(10) + "C=hook", encoding="utf-8")
        with patch.object(env_load, "ROOT", str(root)), patch.object(env_load, "HOOKS", str(root)), \
                patch.dict(os.environ, {"C": "process"}):
            env_load.load_env("h")
            assert (os.environ["A"], os.environ["B"], os.environ["C"]) == ("root", "hook", "process")


def test_log_rotates_when_full():
    import tempfile
    from pathlib import Path
    from core.py import training_log

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        log = training_log.JsonlLog(str(Path(tmp) / "t.jsonl"))
        with patch.object(training_log, "MAX_BYTES", 50):
            log.append({"a": "x" * 60})
            log.append({"a": "y"})
        assert len(Path(log.path + ".1").read_text(encoding="utf-8").splitlines()) == 1
        assert len(log.read_all()) == 1


def test_catalog_reads_skill_files_and_builtins():
    import tempfile
    from pathlib import Path
    from hooks.skill_router import catalog

    def doc(*lines):
        return "\n".join(lines)

    files = {"a": doc("---", "name: alpha", 'description: "Does A. More detail."', "---", "body"),
             "b": doc("---", "name: beta", "description: >", "  Folded text", "  continues here.", "---"),
             "deep/c": doc("---", "name: gamma", "description: C", "disable-model-invocation: true", "---"),
             "d": "no frontmatter"}
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        for name, text in files.items():
            (Path(tmp) / name).mkdir(parents=True, exist_ok=True)
            (Path(tmp) / name / "SKILL.md").write_text(text, encoding="utf-8")
        found = catalog.skills_in(tmp, "p:")
    assert found == {"p:alpha": "Does A", "p:beta": "Folded text continues here", "p:d": ""}
    assert catalog.one_line("x" * 500).endswith("...") and len(catalog.one_line("x" * 500)) == catalog.MAX_DESCRIPTION
    assert dict(catalog.SKILLS).keys() >= set(catalog.BUILTINS)


def test_builtins_check_is_due_monthly():
    import datetime
    import tempfile
    from pathlib import Path
    from hooks.skill_router import builtins

    verified = datetime.date.fromisoformat(builtins.VERIFIED)
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp,             patch.object(builtins._Reminded, "path", str(Path(tmp) / "r.json")):
        assert builtins.due_notice(verified + datetime.timedelta(days=29)) is None
        late = verified + datetime.timedelta(days=31)
        assert "age=31d" in builtins.due_notice(late)
        assert builtins.due_notice(late) is None  # already reminded today
        assert builtins.due_notice(late + datetime.timedelta(days=1)) is not None


def test_skip_rules():
    from core.py.hook_io import should_skip

    for text in ["", "  ", "yes do that please now ok", "go ahead", "fix .env now please"]:
        assert should_skip(text), text
    for text in ["write a long detailed report please", "yes do that please now and then some more"]:
        assert not should_skip(text), text


def test_calibrate_load_reads_rotated_backup():
    import tempfile
    from pathlib import Path
    from core.py.tools import calibrate

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
        (Path(tmp) / "l.jsonl.1").write_text('{"n": 1}\n', encoding="utf-8")
        (Path(tmp) / "l.jsonl").write_text('{"n": 2}\n', encoding="utf-8")
        assert [r["n"] for r in calibrate.load(str(Path(tmp) / "l.jsonl"), "X")] == [1, 2]


def test_latency_percentiles():
    from core.py.tools.calibrate import percentile

    assert percentile([10, 20, 30, 40], 50) == 30
    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([7], 95) == 7


def test_watcher_formats_latency_and_failures():
    from core.py.tools.watch_decisions import format_record

    base = {"timestamp": 1.0, "input_text": "hello", "confidence": 80, "decision": "use", "provider": "jev"}
    timed = format_record({**base, "router": "MODEL", "predicted_size": "large", "elapsed_ms": 412}, 200)
    assert "412ms" in timed and "router-sonnet" in timed
    assert "-" in format_record({**base, "router": "SKILL", "predicted_skill": "pdf"}, 200)  # older record, no timing
    failed = format_record({"timestamp": 1.0, "router": "FAIL", "source": "SKILL", "error": "HTTP 503", "elapsed_ms": 9}, 200)
    assert "SKILL" in failed and "HTTP 503" in failed and "9ms" in failed


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print(f"PASS {name}")
