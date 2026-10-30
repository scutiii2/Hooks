"""The log web view: path safety, host check, prompt hiding, followed status."""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from core.py.tools import web


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "DATA", str(tmp_path))
    monkeypatch.setattr(web.followed_log, "path", str(tmp_path / "core" / "followed.jsonl"))
    for hook in ("skill_router", "core"):
        (tmp_path / hook).mkdir()
    return tmp_path


def _write(path, *records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_resolve_rejects_anything_but_a_log_under_data(data):
    _write(data / "skill_router" / "runs.jsonl", {"timestamp": 1})
    (data / "secret.txt").write_text("x")
    assert web.resolve("skill_router/runs.jsonl")
    for bad in ["../secret.txt", "skill_router/../secret.txt", "skill_router/runs.json", "/etc/passwd",
                "skill_router/missing.jsonl", "runs.jsonl", ""]:
        assert web.resolve(bad) is None, bad


def test_list_logs_and_tail_skip_partial_lines(data):
    path = data / "skill_router" / "runs.jsonl"
    path.write_text('{"timestamp": 1}\n{"timestamp": 2}\n{"timesta', encoding="utf-8")
    assert web.list_logs() == [{"file": "skill_router/runs.jsonl", "size": path.stat().st_size}]
    assert [r["timestamp"] for r in web.tail(str(path), 10)] == [1, 2]
    assert [r["timestamp"] for r in web.tail(str(path), 1)] == [2]


def test_prompts_hidden_unless_asked(data):
    _write(data / "skill_router" / "decisions.jsonl", {"timestamp": 1, "input_text": "private words"})
    assert web.read_log("skill_router/decisions.jsonl", 10, False)[0]["input_text"] == "(hidden)"
    assert web.read_log("skill_router/decisions.jsonl", 10, True)[0]["input_text"] == "private words"
    assert web.read_log("skill_router/nope.jsonl", 10, False) is None


def test_decision_status_followed_pending_ignored(data):
    now = time.time()
    use = {"decision": "use", "session_id": "s", "predicted_skill": "loop"}
    _write(data / "skill_router" / "decisions.jsonl",
           {**use, "timestamp": now - 200}, {**use, "timestamp": now - 100}, {**use, "timestamp": now - 5},
           {"timestamp": now - 1, "decision": "fallback", "session_id": "s"})
    _write(data / "core" / "followed.jsonl",
           {"timestamp": now - 190, "session_id": "s", "tool": "Skill", "target": "loop"})
    status = [r.get("status") for r in web.read_log("skill_router/decisions.jsonl", 10, False)]
    assert status == ["followed", "ignored?", "pending", None]


@pytest.fixture
def server(data):
    httpd = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(url, host=None):
    request = urllib.request.Request(url, headers={"Host": host} if host else {})
    try:
        with urllib.request.urlopen(request) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_http_routes(server, data):
    _write(data / "skill_router" / "runs.jsonl", {"timestamp": 1, "outcome": "use"})
    status, body = _get(server + "/")
    assert status == 200 and b"Hooks" in body
    assert json.loads(_get(server + "/api/logs")[1])[0]["file"] == "skill_router/runs.jsonl"
    assert json.loads(_get(server + "/api/tail?file=skill_router/runs.jsonl")[1])[0]["outcome"] == "use"
    assert _get(server + "/api/tail?file=../x.jsonl")[0] == 404
    assert _get(server + "/api/tail?file=skill_router/runs.jsonl&rows=abc")[0] == 400
    assert _get(server + "/nope")[0] == 404
    assert _get(server + "/api/logs", host="evil.example")[0] == 403


def _post(url, body, ctype="application/json"):
    request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": ctype}, method="POST")
    try:
        with urllib.request.urlopen(request) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_run_commands(server):
    names = [c["name"] for c in json.loads(_get(server + "/api/commands")[1])]
    assert "skill_router" in names and not {"web", "watch", "label"} & set(names)
    assert _post(server + "/api/run", {"name": "web"})[0] == 404
    assert _post(server + "/api/run", {"name": "skill_router"}, "text/plain")[0] == 403
    assert _post(server + "/api/run", {"args": "x"})[0] == 400
    status, body = _post(server + "/api/run", {"name": "skill_router", "args": "status"})
    assert status == 200 and isinstance(body["output"], str) and "code" in body


def test_run_command_strips_quotes_and_uses_no_shell(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return type("Done", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr(web.subprocess, "run", fake_run)
    assert web.run_command("skill_pick", '"two words" plain D:\a\b')["output"] == "ok"
    assert seen["argv"][-3:] == ["two words", "plain", "D:\a\b"]
    assert not seen.get("shell") and seen["timeout"] == web.RUN_TIMEOUT
    assert web.run_command("skill_pick", '"unclosed')["code"] == 2
