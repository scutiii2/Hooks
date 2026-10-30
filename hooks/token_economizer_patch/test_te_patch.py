"""Run: py -m pytest test_te_patch.py (needs git)."""
import json
import subprocess

import te_patch


def _git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


def test_apply_remove_and_conflict(tmp_path, monkeypatch):
    # fake "installed" copy: lib/tokeneconomizer/f.txt, patch adds a line to it
    inst = tmp_path / "inst"
    (inst / "lib" / "tokeneconomizer").mkdir(parents=True)
    f = inst / "lib" / "tokeneconomizer" / "f.txt"
    f.write_text("one\n", newline="\n")
    src = tmp_path / "src"
    (src / "tokeneconomizer").mkdir(parents=True)
    (src / "tokeneconomizer" / "f.txt").write_text("one\n", newline="\n")
    _git(src, "init", "-q")
    _git(src, "-c", "user.email=a@b", "-c", "user.name=t", "add", ".")
    _git(src, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "x")
    (src / "tokeneconomizer" / "f.txt").write_text("one\ntwo\n", newline="\n")
    patch = tmp_path / "p.patch"
    patch.write_bytes(subprocess.run(["git", "diff", "HEAD", "--", "tokeneconomizer"], cwd=src,
                                     capture_output=True, check=True).stdout)
    monkeypatch.setattr(te_patch, "patches", lambda: [patch])

    assert te_patch.state(inst, 'lib')[0] == "missing"
    assert te_patch.apply(inst, 'lib') == "applied now"
    assert f.read_text().splitlines() == ["one", "two"]
    assert te_patch.apply(inst, 'lib') == "applied"          # idempotent
    assert te_patch.remove(inst, 'lib') == "removed"
    assert f.read_text().splitlines() == ["one"]
    f.write_text("changed upstream\n", newline="\n")
    assert te_patch.state(inst, 'lib')[0] == "conflict"


def test_claude_off_flips_setting(tmp_path, monkeypatch):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"enabledPlugins": {te_patch.KEY: True}, "model": "x"}))
    h = te_patch.ClaudeHost()
    monkeypatch.setattr(h, "settings", s)
    h.set_enabled(False)
    assert h.enabled() is False
    assert json.loads(s.read_text())["model"] == "x"


def test_codex_flag_roundtrip(tmp_path, monkeypatch):
    c = tmp_path / "config.toml"
    c.write_text("[other]\nenabled = true\n")
    h = te_patch.CodexHost()
    monkeypatch.setattr(h, "config", c)
    assert h.enabled() is True                      # absent = on
    h.set_enabled(False)
    assert h.enabled() is False
    h.set_enabled(True)
    assert h.enabled() is True
    assert c.read_text().count("[plugins.") == 1 and "[other]\nenabled = true" in c.read_text()


class Fake(te_patch.Host):
    name = "fake"

    def __init__(self, on, tmp):
        self.on, self.dir, self.n = on, tmp, 0

    def targets(self):
        return [(self.dir, "lib")] if self.n else []

    def enabled(self): return self.on

    def install(self):
        self.n += 1
        return True


def test_ensure_installs_only_enabled_hosts(tmp_path, monkeypatch):
    monkeypatch.setattr(te_patch, "apply", lambda t, p: "applied now")
    on, off = Fake(True, tmp_path), Fake(False, tmp_path)
    notes = te_patch.ensure([on, off])
    assert on.n == 1 and off.n == 0
    assert any("installed for fake" in n for n in notes) and any("applied" in n for n in notes)
