"""report (periods, per-hook numbers) and doctor (config checks) on temp data, never the real ~/.claude."""
import json

import pytest

from core.py import paths
from core.py.tools import doctor, manage_hooks, report


def _runs(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA", str(tmp_path))
    monkeypatch.setattr(report, "DATA", str(tmp_path))
    monkeypatch.setattr(report.followed_log, "path", str(tmp_path / "core" / "followed.jsonl"))
    return tmp_path


def test_report_splits_periods_and_counts_outcomes(data):
    _runs(data / "hook_a" / "runs.jsonl",
          {"timestamp": 100, "outcome": "x", "duration_ms": 10},
          {"timestamp": 300, "outcome": "y", "duration_ms": 30},
          {"timestamp": 400, "outcome": "y", "duration_ms": 50})
    out = "\n".join(report.build(["--split", "200"], now=500))
    assert "before 200" in out and "1 runs, avg 10 ms" in out
    assert "since 200" in out and "2 runs, avg 40 ms, p95 50 ms | y 2" in out
    assert "no runs" not in out
    assert report.build(["--hook", "missing"], now=500) == ["no run logs yet"]


def test_report_noise_filter_bytes_and_skill_follow_rate(data):
    _runs(data / "noise_filter" / "runs.jsonl",
          {"timestamp": 1, "event": "Filter", "bytes_in": 1000, "bytes_out": 400, "duration_ms": 1})
    _runs(data / "skill_router" / "runs.jsonl", {"timestamp": 1, "outcome": "use", "duration_ms": 1})
    _runs(data / "skill_router" / "decisions.jsonl",
          {"timestamp": 1, "decision": "use", "session_id": "s", "confidence": 90, "skill": "a"})
    _runs(data / "core" / "followed.jsonl", {"timestamp": 2, "session_id": "s", "skill": "a", "tool": "Skill"})
    out = "\n".join(report.build([], now=10))
    assert "removed 60% of bytes" in out
    assert "followed 1/1 (100%)" in out


def test_report_rejects_bad_split():
    with pytest.raises(SystemExit):
        report.periods(["--split", "soon"], 1)


def test_doctor_flags_missing_file_and_absent_hooks(tmp_path):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [
        {"type": "command", "command": "C:/nope/pythonw.exe", "args": ["C:/nope/x.py"]}]}]}}))
    levels = dict((text, level) for level, text in doctor.check_config("claude", str(cfg)))
    assert any(l == doctor.FAIL and "C:/nope/x.py" in t for t, l in levels.items())
    assert any(l == doctor.WARN and "not installed" in t for t, l in levels.items())


def test_doctor_ok_when_our_hooks_are_installed_and_files_exist(tmp_path, monkeypatch):
    real = tmp_path / "py.exe"
    real.write_text("x")
    handler = {"type": "command", "command": str(real).replace("\\", "/"), "args": []}
    monkeypatch.setattr(manage_hooks, "GROUPS", {"claude": [("Stop", None, [handler])]})
    cfg = tmp_path / "s.json"
    cfg.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [handler]}]}}))
    assert doctor.check_config("claude", str(cfg))[0][0] == doctor.OK
    assert doctor.check_config("claude", str(tmp_path / "none.json"))[0][0] == doctor.WARN
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert doctor.check_config("claude", str(bad))[0][0] == doctor.FAIL


def test_skill_table_orders_least_followed_first():
    def use(i, skill, sid):
        return {"timestamp": i, "decision": "use", "session_id": sid, "predicted_skill": skill, "confidence": 90}
    decisions = [use(i, "good", f"g{i}") for i in range(5)] + [use(10 + i, "bad", f"b{i}") for i in range(5)]
    actions = [{"timestamp": i + 1, "session_id": f"g{i}", "target": "good", "tool": "Skill"} for i in range(5)]
    rows = report.skill_table(decisions, actions)
    assert rows[0].startswith("bad") and "0/5" in rows[0] and rows[1].startswith("good") and "5/5" in rows[1]


def test_fix_installs_hooks_after_asking(tmp_path, monkeypatch, capsys):
    handler = {"type": "command", "command": "py", "args": ["x"]}
    target = tmp_path / "s.json"
    monkeypatch.setattr(manage_hooks, "GROUPS", {"claude": [("Stop", None, [handler])], "codex": []})
    monkeypatch.setattr(manage_hooks, "CLAUDE_TARGET", str(target))
    monkeypatch.setattr(manage_hooks, "CODEX_TARGET", str(tmp_path / "none.json"))
    monkeypatch.setattr(doctor, "venv_python", lambda: __file__)  # pretend the venv exists
    monkeypatch.setattr(doctor.transfer, "_gcm", lambda: object())  # and cryptography: --yes must not pip install
    monkeypatch.setattr(doctor, "check_te", lambda: [])  # and no CLI or plugin to install
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    doctor.main(["--fix"])
    assert not target.exists()  # said no: nothing written
    doctor.main(["--fix", "--yes"])
    assert json.loads(target.read_text())["hooks"]["Stop"][0]["hooks"] == [handler]


def test_te_checks_warn_and_offer_a_fix(monkeypatch):
    class Fake:
        HOSTS = []

        def health(self):
            return [("warn", "codex: CLI not on PATH, so x", "cli"), ("ok", "claude: TokenEconomizer installed", "")]

        def install_cli(self, names, yes=False):
            installed.append((names, yes))

    installed = []
    monkeypatch.setattr(doctor, "te_patch", lambda: Fake())
    assert doctor.check_te() == [(doctor.WARN, "codex: CLI not on PATH, so x", "cli"), (doctor.OK, "claude: TokenEconomizer installed", "")]
    monkeypatch.setattr(doctor, "check_config", lambda host, target: [])
    monkeypatch.setattr(doctor, "venv_python", lambda: __file__)
    monkeypatch.setattr(doctor.transfer, "_gcm", lambda: object())
    todo = doctor.fixes()
    assert [w for w, _ in todo] == ["install the codex CLI with its official installer"]
    todo[0][1]()
    assert installed == [(["codex"], True)]


def test_stats_counts_the_window_the_day_before_and_the_outcome_classes(data):
    day = 86400
    _runs(data / "hook_a" / "runs.jsonl",
          {"timestamp": 10, "event": "Stop", "outcome": "injected", "duration_ms": 4},   # the day before
          {"timestamp": day + 10, "event": "Stop", "outcome": "injected", "duration_ms": 4},
          {"timestamp": day + 20, "event": "Stop", "outcome": "nothing", "duration_ms": 8},
          {"timestamp": day + 30, "event": "Stop", "outcome": "failed", "duration_ms": 12})
    s = report.stats(1, now=2 * day)
    h = s["hooks"][0]
    assert (h["name"], h["event"], h["runs"], h["ok"], h["warn"], h["bad"], h["median_ms"]) == ("hook_a", "Stop", 3, 1, 1, 1, 8)
    assert s["totals"]["prev_runs"] == 1 and s["totals"]["failed"] == 1 and s["totals"]["slowest"]["name"] == "hook_a"
    assert s["follow"] == {"followed": 0, "total": 0, "least": ""}
    assert [report.outcome_class(w) for w in ("use", "skipped", "error: x", None)] == ["ok", "warn", "bad", "warn"]
