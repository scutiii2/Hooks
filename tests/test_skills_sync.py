"""skills_sync on a fake home: nothing here touches the real ~/.claude or ~/.codex."""
import json
import os
import zipfile
from pathlib import Path

import pytest

from core.py.tools import skills_sync as s

CONFIG = '''model = "x"

[marketplaces.caveman]
source_type = "git"
source = "https://github.com/a/caveman.git"

[marketplaces.local-one]
source_type = "local"
source = 'C:\\somewhere'

[plugins."caveman@caveman"]
enabled = true

[plugins."doc@local-one"]
enabled = true

[windows]
sandbox = "unelevated"
'''


@pytest.fixture
def env(tmp_path):
    e = s.Env(claude=tmp_path / "c", codex=tmp_path / "x", store=tmp_path / "ws" / ".agents" / "skills",
              roots=[tmp_path / "ws"], trash=tmp_path / "trash")
    for h in e.homes.values():
        h.mkdir(parents=True)
    e.store.mkdir(parents=True)
    (e.claude / "plugins").mkdir()
    try:
        os.symlink(e.store, tmp_path / "probe", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not allowed here")
    return e


def skill(folder: Path, name: str, text="x") -> Path:
    (folder / name).mkdir(parents=True, exist_ok=True)
    (folder / name / "SKILL.md").write_text(text)
    return folder / name


def link(e, side, target):
    os.symlink(target, e.homes[side] / target.name, target_is_directory=True)


def status(e):
    return {r["name"]: r["status"] for r in s.scan_skills(e)}


def test_scan_statuses_and_non_skill_folders(env):
    link(env, "claude", skill(env.store, "both")); link(env, "codex", env.store / "both")
    link(env, "claude", skill(env.store, "lonely"))
    link(env, "codex", skill(env.store, "other"))
    (env.claude / "skills" / "synced").mkdir()  # no SKILL.md: the Claude app's own folder
    assert status(env) == {"both": "ok", "lonely": "claude only", "other": "codex only"}


def test_sync_links_missing_side_adopts_real_folder_and_skips_project_skills(env, tmp_path):
    link(env, "codex", skill(env.store, "inStore"))
    skill(env.homes["claude"], "realFolder")
    link(env, "codex", skill(tmp_path / "ws" / "proj" / ".agents" / "skills", "projOnly"))
    plan = {p["name"]: p for p in s.sync_skills(env, dry_run=True)}
    assert not (env.claude / "skills" / "inStore").exists()  # dry run changed nothing
    assert plan["projOnly"]["ok"] is False
    s.sync_skills(env, dry_run=False)
    assert status(env) == {"inStore": "ok", "realFolder": "ok", "projOnly": "codex only"}
    assert (env.store / "realFolder" / "SKILL.md").is_file()


def test_delete_skill_removes_links_and_source_and_restores(env):
    src = skill(env.store, "gone")
    link(env, "claude", src); link(env, "codex", src)
    plan = s.delete_skill(env, "gone")["plan"]
    assert len(plan) == 3 and src.exists()
    out = s.delete_skill(env, "gone", dry_run=False)
    assert not src.exists() and not os.path.lexists(env.claude / "skills" / "gone") and not os.path.lexists(env.codex / "skills" / "gone")
    s.restore(env, out["trash"])
    assert (env.store / "gone" / "SKILL.md").is_file() and status(env) == {"gone": "ok"}


def test_delete_skill_rejects_bad_names_and_unknown(env):
    for bad in ("../x", "a/b", ".hidden", ""):
        with pytest.raises(ValueError):
            s.delete_skill(env, bad)
    with pytest.raises(ValueError, match="no skill"):
        s.delete_skill(env, "nothing")


def setup_plugins(env):
    (env.claude / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {"caveman@caveman": [{"scope": "user"}], "pony@pony": [{"scope": "user"}]}}))
    (env.claude / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"caveman@caveman": True, "pony@pony": True},
         "extraKnownMarketplaces": {"pony": {"source": {"source": "git", "url": "https://github.com/a/pony.git"}}}}))
    (env.codex / "config.toml").write_text(CONFIG)


def test_scan_plugins(env):
    setup_plugins(env)
    rows = {r["id"]: (r["claude"], r["codex"]) for r in s.scan_plugins(env)}
    assert rows == {"caveman@caveman": ("on", "on"), "pony@pony": ("on", None), "doc@local-one": (None, "on")}


def test_delete_plugin_from_both_keeps_the_rest_and_restores(env):
    setup_plugins(env)
    assert len(s.delete_plugin(env, "caveman@caveman")["plan"]) == 3
    out = s.delete_plugin(env, "caveman@caveman", dry_run=False)
    assert {r["id"] for r in s.scan_plugins(env)} == {"pony@pony", "doc@local-one"}
    text = (env.codex / "config.toml").read_text()
    assert '[plugins."doc@local-one"]' in text and "[windows]" in text and "caveman@caveman" not in text
    s.restore(env, out["trash"])
    assert {r["id"] for r in s.scan_plugins(env)} == {"caveman@caveman", "pony@pony", "doc@local-one"}


def test_delete_plugin_purge_cache(env):
    setup_plugins(env)
    cache = env.claude / "plugins" / "cache" / "pony" / "pony" / "1.0"
    cache.mkdir(parents=True)
    s.delete_plugin(env, "pony@pony", purge_cache=True, dry_run=False)
    assert not (env.claude / "plugins" / "cache" / "pony" / "pony").exists()


def test_add_plugin_to_the_other_tool(env):
    setup_plugins(env)
    s.add_plugin(env, "pony@pony", "codex", dry_run=False)
    text = (env.codex / "config.toml").read_text()
    assert '[plugins."pony@pony"]' in text and "[marketplaces.pony]" in text
    assert {r["id"]: r["codex"] for r in s.scan_plugins(env)}["pony@pony"] == "on"
    with pytest.raises(ValueError, match="local"):
        s.add_plugin(env, "doc@local-one", "claude")  # local marketplace cannot be copied
    with pytest.raises(ValueError, match="not installed"):
        s.add_plugin(env, "zzz@pony", "claude")


def test_promote_skill_modes(env, tmp_path):
    proj = tmp_path / "ws" / "proj" / ".agents" / "skills"
    src = skill(proj, "mine", "project copy")
    assert not (env.store / "mine").exists() and len(s.promote_skill(env, str(src))["plan"]) == 3
    out = s.promote_skill(env, str(src), "link", dry_run=False)
    assert (env.store / "mine" / "SKILL.md").read_text() == "project copy"
    assert status(env) == {"mine": "ok"}
    assert os.path.realpath(src) == os.path.realpath(env.store / "mine") and out["trash"]
    other = skill(tmp_path / "ws" / "p2" / ".agents" / "skills", "mine", "different")
    with pytest.raises(ValueError, match="already exists"):
        s.promote_skill(env, str(other), dry_run=False)
    s.promote_skill(env, str(other), "remove", overwrite=True, dry_run=False)
    assert (env.store / "mine" / "SKILL.md").read_text() == "different" and not other.exists()
    with pytest.raises(ValueError, match="not a project skill"):
        s.promote_skill(env, str(tmp_path))


def test_scan_projects_finds_project_only_skills_and_plugins(env, tmp_path):
    link(env, "claude", skill(env.store, "glob"))
    skill(tmp_path / "ws" / "proj" / ".agents" / "skills", "local")
    (tmp_path / "ws" / "proj" / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ws" / "proj" / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"x@y": True}}))
    skill(tmp_path / "ws" / "node_modules" / "pkg" / ".agents" / "skills", "ignored")
    found = s.scan_projects(env)
    assert {(x["name"], x["global"]) for x in found["skills"]} == {("glob", True), ("local", False)}
    assert [(p["project"], p["id"]) for p in found["plugins"]] == [("proj", "x@y")]


def test_promote_plugin_moves_it_to_user_settings(env, tmp_path):
    setup_plugins(env)
    proj = tmp_path / "ws" / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"new@mk": True}, "extraKnownMarketplaces": {"mk": {"source": {"source": "git", "url": "u"}}}}))
    s.promote_plugin(env, str(proj), "new@mk", dry_run=False)
    user = json.loads((env.claude / "settings.json").read_text())
    assert user["enabledPlugins"]["new@mk"] is True and "mk" in user["extraKnownMarketplaces"]
    assert "new@mk" not in json.loads((proj / ".claude" / "settings.json").read_text())["enabledPlugins"]


@pytest.mark.parametrize("password", ["", "pw"])
def test_export_import_round_trip(env, tmp_path, password):
    setup_plugins(env)
    src = skill(env.store, "kept", "v1"); link(env, "claude", src); link(env, "codex", src)
    proj = skill(tmp_path / "ws" / "proj" / ".agents" / "skills", "extra", "p")
    out = s.export_bundle(env, str(tmp_path / "out"), password, [str(proj)])
    assert out["skills"] == 2 and out["file"].endswith(".hbk" if password else ".zip")
    (env.store / "kept" / "SKILL.md").write_text("changed")
    dry = s.import_bundle(env, out["file"], password)
    assert any("kept" in p for p in dry["plan"]) and (env.store / "kept" / "SKILL.md").read_text() == "changed"
    done = s.import_bundle(env, str(tmp_path / "out"), password, dry_run=False)
    assert (env.store / "kept" / "SKILL.md").read_text() == "v1" and (env.store / "extra" / "SKILL.md").is_file()
    assert status(env) == {"kept": "ok", "extra": "ok"}
    assert any("doc@local-one" in n for n in done["notes"])  # local marketplace skipped, not written


def test_import_refuses_missing_password_and_path_escape(env, tmp_path):
    out = s.export_bundle(env, str(tmp_path / "o"), "pw")
    with pytest.raises(ValueError, match="password"):
        s.import_bundle(env, out["file"])
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("skills/x/../../../evil.txt", "x")
    with pytest.raises(ValueError, match="unsafe"):
        s.import_bundle(env, str(bad))


def test_handle_defaults_to_dry_run_and_rejects_unknown(env):
    src = skill(env.store, "keepme"); link(env, "claude", src)
    assert s.handle("delete_skill", {"name": "keepme"}, env)["plan"]
    assert src.exists()
    with pytest.raises(ValueError):
        s.handle("nope", {}, env)
