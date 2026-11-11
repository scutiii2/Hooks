"""Export/import of .data and .memory as a zip (optionally encrypted), plus the web endpoints."""
import json
import os
import threading
import urllib.error
import urllib.request
import zipfile

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


def _damage(data, memory):
    (data / "skill_router" / "state.json").write_text("changed")
    (memory / "core" / "labeled.jsonl").unlink()


def _restored(data, memory):
    assert (data / "skill_router" / "state.json").read_text() == '{"enabled": true}'
    assert (memory / "core" / "labeled.jsonl").read_text() == "x\n"


def test_zip_round_trip(roots, tmp_path):
    out = transfer.export_to(str(tmp_path / "backup"))
    assert (out["data"], out["memory"]) == (1, 1) and out["file"].endswith(".zip")
    with zipfile.ZipFile(out["file"]) as z:
        assert sorted(z.namelist()) == ["data/skill_router/state.json", "memory/core/labeled.jsonl"]
    _damage(*roots)
    assert transfer.import_from(out["file"])["data"] == 1  # by file
    _restored(*roots)
    _damage(*roots)
    assert transfer.import_from(str(tmp_path / "backup"))["file"] == out["file"]  # by folder: newest backup
    _restored(*roots)


def test_encrypted_round_trip(roots, tmp_path):
    out = transfer.export_to(str(tmp_path / "b"), "s3cret")
    assert out["file"].endswith(".hbk")
    blob = open(out["file"], "rb").read()
    assert b"labeled" not in blob and b"PK" not in blob[:2]  # nothing readable
    _damage(*roots)
    with pytest.raises(ValueError, match="password"):
        transfer.import_from(out["file"])
    with pytest.raises(ValueError, match="wrong password"):
        transfer.import_from(out["file"], "nope")
    transfer.import_from(out["file"], "s3cret")
    _restored(*roots)


def test_tampered_encrypted_file_is_rejected(roots, tmp_path):
    path = transfer.export_to(str(tmp_path / "b"), "pw")["file"]
    blob = bytearray(open(path, "rb").read())
    blob[len(transfer.MAGIC) + 40] ^= 1
    open(path, "wb").write(blob)
    with pytest.raises(ValueError, match="damaged"):
        transfer.import_from(path, "pw")


def test_zip_with_path_escape_is_refused(roots, tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("data/../../evil.txt", "x")
    with pytest.raises(ValueError, match="unsafe"):
        transfer.import_from(str(bad))
    assert not (tmp_path / "evil.txt").exists()


def test_plain_folder_copy_still_imports(roots, tmp_path):
    folder = tmp_path / "old"
    (folder / "data" / "x").mkdir(parents=True)
    (folder / "data" / "x" / "f.json").write_text("1")
    assert transfer.import_from(str(folder))["data"] == 1
    assert os.path.exists(os.path.join(paths.DATA, "x", "f.json"))


def test_bad_inputs(roots, tmp_path):
    notzip = tmp_path / "x.zip"
    notzip.write_text("hello")
    for bad, fn in [("", transfer.export_to), (str(tmp_path / "nope"), transfer.import_from),
                    (str(tmp_path), transfer.import_from), (str(notzip), transfer.import_from)]:
        with pytest.raises(ValueError):
            fn(bad)


def test_endpoint_rejects_foreign_host(roots, tmp_path):
    server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/api/export"
    try:
        req = urllib.request.Request(url, json.dumps({"folder": str(tmp_path / "o"), "password": "pw"}).encode(),
                                     {"Content-Type": "application/json"})
        files = json.load(urllib.request.urlopen(req))["files"]
        assert (files["data"], files["memory"]) == (1, 1) and files["file"].endswith(".hbk")
        req = urllib.request.Request(url, b"{}", {"Content-Type": "text/plain"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
    finally:
        server.shutdown()
