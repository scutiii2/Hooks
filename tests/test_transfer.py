"""Export/import of .data and .memory through the web endpoints."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from core.py import paths
from core.py.tools import transfer, web


@pytest.fixture
def roots(tmp_path, monkeypatch):
    data, memory = tmp_path / "d", tmp_path / "m"
    (data / "skill_router").mkdir(parents=True)
    (memory / "core").mkdir(parents=True)
    (data / "skill_router" / "state.json").write_text('{"enabled": true}')
    (memory / "core" / "labeled.jsonl").write_text("x\n")
    monkeypatch.setattr(paths, "DATA", str(data))
    monkeypatch.setattr(paths, "MEMORY", str(memory))
    return data, memory


def test_round_trip(roots, tmp_path):
    data, memory = roots
    out = tmp_path / "backup"
    assert transfer.export_to(str(out)) == {"data": 1, "memory": 1}
    (data / "skill_router" / "state.json").write_text("changed")
    (memory / "core" / "labeled.jsonl").unlink()
    assert transfer.import_from(str(out)) == {"data": 1, "memory": 1}
    assert (data / "skill_router" / "state.json").read_text() == '{"enabled": true}'
    assert (memory / "core" / "labeled.jsonl").read_text() == "x\n"


def test_bad_folders(roots, tmp_path):
    for bad, fn in [("", transfer.export_to), (str(tmp_path / "nope"), transfer.import_from),
                    (str(tmp_path), transfer.import_from)]:
        with pytest.raises(ValueError):
            fn(bad)


def test_endpoint_rejects_foreign_host(roots, tmp_path):
    server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/api/export"
    try:
        req = urllib.request.Request(url, json.dumps({"folder": str(tmp_path / "o")}).encode(),
                                     {"Content-Type": "application/json"})
        assert json.load(urllib.request.urlopen(req)) == {"files": {"data": 1, "memory": 1}}
        req = urllib.request.Request(url, b"{}", {"Content-Type": "text/plain"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
    finally:
        server.shutdown()
