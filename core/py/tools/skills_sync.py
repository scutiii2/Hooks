"""Skills and plugins of Claude Code and Codex: scan, sync, delete (to trash), make global, export, import.

Skills: the real folders live in `store` (the workspace's `.agents/skills`); `~/.claude/skills/<name>` and
`~/.codex/skills/<name>` are links to them (the layout hooks/source_of_truth builds). A project skill is a folder
in some project's `.agents/skills` or `.claude/skills` that no global link points at.
Plugins: Claude keeps them in `plugins/installed_plugins.json` + `settings.json` (`enabledPlugins`,
`extraKnownMarketplaces`), Codex in `config.toml` (`[plugins."id"]`, `[marketplaces.name]`).

Nothing is erased: deleted folders and every edited config file go to `trash/<time>/` with a manifest, and
`restore` puts them back. Every change takes `dry_run` (default True in `handle`) and returns its plan.
"""
import io
import json
import os
import re
import shutil
import time
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from . import transfer

NAME = re.compile(r"^[\w][\w.-]*$")
PLUGIN_ID = re.compile(r"^[\w.-]+@[\w.-]+$")
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".data", ".memory", "dist", "build"}
MAX_DEPTH = 4
PREFIX = "hooks-skills-"


def _default_store() -> Path:
    return Path(paths.ROOT).parents[1] / ".agents" / "skills"


@dataclass
class Env:
    claude: Path = field(default_factory=lambda: Path.home() / ".claude")
    codex: Path = field(default_factory=lambda: Path.home() / ".codex")
    store: Path = field(default_factory=_default_store)
    roots: list = field(default_factory=lambda: [_default_store().parents[1]])
    trash: Path = field(default_factory=lambda: Path(paths.DATA) / "trash")

    @property
    def homes(self) -> dict:
        return {"claude": self.claude / "skills", "codex": self.codex / "skills"}


# ---------------------------------------------------------------- small helpers

def _check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME.match(name):
        raise ValueError(f"bad name: {name!r}")
    return name


def _check_plugin(plugin: str) -> str:
    if not isinstance(plugin, str) or not PLUGIN_ID.match(plugin):
        raise ValueError(f"bad plugin id: {plugin!r} (want name@marketplace)")
    return plugin


def _is_link(p: Path) -> bool:
    """A symlink or an NTFS junction (the links under ~/.claude/skills are junctions)."""
    return p.is_symlink() or os.path.isjunction(p)


def _kind(p: Path) -> str | None:
    if _is_link(p):
        return "link" if p.exists() else "broken"
    return "dir" if p.is_dir() else None


def _real(p: Path) -> str:
    return os.path.normcase(os.path.realpath(p))


def _link(target: Path, link: Path) -> None:
    """Make `link` a symlink to `target`, replacing a link that is already there."""
    if link.is_symlink():
        link.unlink()
    elif os.path.isjunction(link):
        os.rmdir(link)  # removes the junction, not its target
    elif link.exists():
        raise ValueError(f"{link} is a real folder; not replacing it")
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as e:
        raise ValueError(f"cannot link {link} ({e}); on Windows turn on Developer Mode") from None


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class Trash:
    """One bucket per change: moved folders and backed-up files, plus manifest.json for `restore`."""

    def __init__(self, env: Env):
        self.dir = env.trash / time.strftime("%Y%m%d-%H%M%S")
        self.items: list = []

    def _slot(self, name: str) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        n, slot = 0, self.dir / f"{len(self.items):02d}-{name}"
        while slot.exists():
            n += 1
            slot = self.dir / f"{len(self.items):02d}-{n}-{name}"
        return slot

    def move(self, path: Path) -> None:
        slot = self._slot(path.name)
        shutil.move(str(path), str(slot))
        self.items.append({"orig": str(path), "saved": str(slot), "kind": "moved"})

    def backup(self, path: Path) -> None:
        if path.exists():
            slot = self._slot(path.name)
            shutil.copy2(path, slot)
            self.items.append({"orig": str(path), "saved": str(slot), "kind": "backup"})

    def save(self) -> str:
        if self.items:
            (self.dir / "manifest.json").write_text(json.dumps(self.items, indent=2), encoding="utf-8")
        return self.dir.name if self.items else ""


def trash_list(env: Env) -> list:
    out = []
    for d in sorted(env.trash.glob("*"), reverse=True) if env.trash.is_dir() else []:
        items = _read_json(d / "manifest.json", [])
        if items:
            out.append({"id": d.name, "items": [i["orig"] for i in items]})
    return out


def restore(env: Env, bucket: str) -> list:
    """Put a bucket back: moved folders return (refused if the place is taken), backed-up files overwrite."""
    d = env.trash / _check_name(bucket)
    items = _read_json(d / "manifest.json", None)
    if not items:
        raise ValueError("nothing to restore in that bucket")
    taken = [i["orig"] for i in items if i["kind"] == "moved" and (os.path.lexists(i["orig"]))]
    if taken:
        raise ValueError(f"already exists, not restoring over it: {taken[0]}")
    for i in reversed(items):
        orig = Path(i["orig"])
        orig.parent.mkdir(parents=True, exist_ok=True)
        if i["kind"] == "moved":
            shutil.move(i["saved"], str(orig))
        else:
            shutil.copy2(i["saved"], orig)
    (d / "manifest.json").rename(d / "manifest.restored.json")
    return [i["orig"] for i in items]


# ---------------------------------------------------------------- scan

def scan_skills(env: Env) -> list:
    homes, names = env.homes, set()
    for h in homes.values():
        if h.is_dir():
            # only folders with a SKILL.md (or dead links) are skills: `synced/` belongs to the Claude app
            names |= {e.name for e in h.iterdir() if not e.name.startswith(".") and ((e / "SKILL.md").is_file() or _kind(e) == "broken")}
    rows = []
    for name in sorted(names):
        side = {s: _kind(h / name) for s, h in homes.items()}
        reals = {_real(homes[s] / name) for s, k in side.items() if k in ("link", "dir")}
        if "broken" in side.values():
            status = "broken link"
        elif side["claude"] is None or side["codex"] is None:
            status = "codex only" if side["claude"] is None else "claude only"
        else:
            status = "ok" if len(reals) == 1 else "conflict"
        source = next((str(Path(os.path.realpath(homes[s] / name))) for s in homes if side[s] in ("link", "dir")), None)
        rows.append({"name": name, "claude": side["claude"], "codex": side["codex"], "status": status, "source": source,
                     "in_store": bool(source) and os.path.normcase(source).startswith(_real(env.store))})
    return rows


def _walk_projects(env: Env):
    """Yield every project folder under the roots (depth-limited, skipping build and cache folders)."""
    for root in env.roots:
        root = Path(root)
        if not root.is_dir():
            continue
        base = len(root.parts)
        for cur, dirs, _ in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]  # .agents/.claude are read directly
            if len(Path(cur).parts) - base >= MAX_DEPTH:
                dirs[:] = []
            yield Path(cur)


def scan_projects(env: Env) -> dict:
    """Skills that no global link points at, and plugins switched on in a project's settings."""
    home = env.homes["claude"]
    globals_ = {_real(e) for e in (home.iterdir() if home.is_dir() else []) if not e.name.startswith(".")}
    codex = env.homes["codex"]
    codex_linked = {_real(e) for e in (codex.iterdir() if codex.is_dir() else []) if not e.name.startswith(".")}
    skills, seen, plugins = [], set(), []
    for proj in _walk_projects(env):
        for sub in (".agents/skills", ".claude/skills"):
            folder = proj / sub
            if not folder.is_dir():
                continue
            for e in sorted(folder.iterdir()):
                real = _real(e)
                if (e / "SKILL.md").is_file() and not e.name.startswith(".") and real not in seen:
                    seen.add(real)
                    skills.append({"name": e.name, "project": proj.name, "path": str(e),
                                   "global": real in globals_ or real.startswith(_real(env.store)),
                                   "codex_linked": real in codex_linked})
        for name in ("settings.json", "settings.local.json"):
            enabled = _read_json(proj / ".claude" / name, {}).get("enabledPlugins")
            for pid, on in (enabled.items() if isinstance(enabled, dict) else []):
                plugins.append({"project": proj.name, "path": str(proj), "id": pid, "enabled": bool(on), "file": name})
    return {"skills": skills, "plugins": plugins}


def _marketplaces(env: Env) -> dict:
    """name -> {"type": "git"|"local", "url": str} from both tools; Claude's wins when both have it."""
    out = {}
    for name, m in _toml(env.codex / "config.toml").get("marketplaces", {}).items():
        out[name] = {"type": m.get("source_type", "git"), "url": m.get("source", "")}
    sources = {**_read_json(env.claude / "plugins" / "known_marketplaces.json", {}),
               **_read_json(env.claude / "settings.json", {}).get("extraKnownMarketplaces", {})}
    for name, m in sources.items():
        s = m.get("source", {}) if isinstance(m, dict) else {}
        if s.get("source") == "git" and s.get("url"):
            out[name] = {"type": "git", "url": s["url"]}
        elif s.get("source") == "github" and s.get("repo"):
            out[name] = {"type": "git", "url": f"https://github.com/{s['repo']}.git"}
    return out


def scan_plugins(env: Env) -> list:
    installed = _read_json(env.claude / "plugins" / "installed_plugins.json", {}).get("plugins", {})
    enabled = _read_json(env.claude / "settings.json", {}).get("enabledPlugins", {})
    codex = _toml(env.codex / "config.toml").get("plugins", {})
    rows = []
    for pid in sorted(set(installed) | set(enabled) | set(codex)):
        if pid in installed or pid in enabled:
            claude = "on" if enabled.get(pid, pid in installed) else "off"
        else:
            claude = None
        c = codex.get(pid)
        rows.append({"id": pid, "claude": claude, "codex": None if c is None else ("on" if c.get("enabled", True) else "off"),
                     "marketplace": pid.split("@")[-1]})
    return rows


def scan(env: Env) -> dict:
    return {"skills": scan_skills(env), "plugins": scan_plugins(env), "project": scan_projects(env),
            "trash": trash_list(env)}


# ---------------------------------------------------------------- skills: sync, delete, promote

def sync_skills(env: Env, dry_run: bool = True) -> list:
    """Make each skill present in both tools and linked to one real folder in `store`."""
    plan, homes, trash = [], env.homes, Trash(env)
    for row in scan_skills(env):
        name, status = row["name"], row["status"]
        if status == "ok":
            continue
        if status not in ("claude only", "codex only"):
            plan.append({"name": name, "action": "skip", "note": f"{status}: fix by hand", "ok": False})
            continue
        if not row["in_store"] and _kind(homes["codex" if status == "claude only" else "claude"] / name) is None                 and status == "codex only":
            plan.append({"name": name, "action": "skip", "ok": False,
                         "note": "project skill linked only into Codex: use Make global to add it to both"})
            continue
        have = "claude" if status == "claude only" else "codex"
        missing = "codex" if have == "claude" else "claude"
        src, move = Path(row["source"]), False
        if _kind(homes[have] / name) == "dir":  # a real folder in one tool: adopt it into the store
            target, move = env.store / name, True
            if target.exists():
                plan.append({"name": name, "action": "skip", "note": f"{target} already exists", "ok": False})
                continue
        else:
            target = src
        plan.append({"name": name, "action": f"adopt into store, link {have} and {missing}" if move
                     else f"link {missing} to {target}", "ok": True})
        if dry_run:
            continue
        if move:
            env.store.mkdir(parents=True, exist_ok=True)
            shutil.move(str(homes[have] / name), str(target))
            _link(target, homes[have] / name)
        _link(target, homes[missing] / name)
    return plan


def delete_skill(env: Env, name: str, dry_run: bool = True) -> dict:
    """Trash the skill from both tools: the two links (or folders) and the real folder they point at."""
    _check_name(name)
    victims, sources = [], []
    for h in env.homes.values():
        p = h / name
        if _kind(p):
            victims.append(p)
            real = Path(os.path.realpath(p))
            if _is_link(p) and real.exists() and real not in sources:
                sources.append(real)
    if not victims:
        raise ValueError(f"no skill named {name} in Claude or Codex")
    plan = [str(p) for p in victims + sources]
    if not dry_run:
        t = Trash(env)
        for p in victims + sources:
            if os.path.lexists(p):
                t.move(p)
        return {"plan": plan, "trash": t.save()}
    return {"plan": plan}


def promote_skill(env: Env, path: str, mode: str = "link", overwrite: bool = False, dry_run: bool = True) -> dict:
    """Copy a project skill into the store and link it from both tools. mode: keep | link | remove (the project copy)."""
    src = Path(path)
    if not src.is_dir() or not (src.parent.name == "skills" and src.parent.parent.name in (".agents", ".claude")):
        raise ValueError("not a project skill folder (.agents/skills/<name> or .claude/skills/<name>)")
    if mode not in ("keep", "link", "remove"):
        raise ValueError("mode must be keep, link or remove")
    name, dest = _check_name(src.name), env.store / src.name
    if dest.exists() and _real(dest) != _real(src) and not overwrite:
        raise ValueError(f"a global skill named {name} already exists; tick overwrite to replace it")
    plan = [f"copy {src} to {dest}", f"link {env.claude / 'skills' / name} and {env.codex / 'skills' / name} to it",
            {"keep": "keep the project copy", "link": "replace the project copy with a link to the global one",
             "remove": "move the project copy to trash"}[mode]]
    if dry_run:
        return {"plan": plan}
    t = Trash(env)
    already = dest.exists() and _real(dest) == _real(src)
    if not already:
        if dest.exists():
            t.move(dest)
        env.store.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, symlinks=True)
    for h in env.homes.values():
        if _kind(h / name) == "dir":
            t.move(h / name)
        _link(dest, h / name)
    if not already and mode != "keep":
        t.move(src)
        if mode == "link":
            _link(dest, src)
    return {"plan": plan, "trash": t.save()}


# ---------------------------------------------------------------- plugins: add, delete, promote

def _toml_block(pid: str) -> re.Pattern:
    return re.compile(r'^\[plugins\."' + re.escape(pid) + r'"\][^\n]*\n(?:(?!\[)[^\n]*\n?)*', re.M)


def _codex_add(text: str, pid: str, mp: str, source: dict | None) -> str:
    if f"[marketplaces.{mp}]" not in text and source:
        text = text.rstrip("\n") + f'\n\n[marketplaces.{mp}]\nsource_type = "git"\nsource = "{source["url"]}"\n'
    if not _toml_block(pid).search(text):
        text = text.rstrip("\n") + f'\n\n[plugins."{pid}"]\nenabled = true\n'
    return text


def add_plugin(env: Env, pid: str, to: str, dry_run: bool = True) -> dict:
    """Copy a plugin entry (and its marketplace) from the other tool's config into `to`'s."""
    _check_plugin(pid)
    if to not in ("claude", "codex"):
        raise ValueError("to must be claude or codex")
    mp = pid.split("@")[1]
    row = next((r for r in scan_plugins(env) if r["id"] == pid), None)
    other = "codex" if to == "claude" else "claude"
    if not row or not row[other]:
        raise ValueError(f"{pid} is not installed in {other}")
    source = _marketplaces(env).get(mp)
    if not source or source["type"] != "git":
        raise ValueError(f"marketplace {mp} is local to one machine or unknown: add it by hand")
    plan = [f"add {pid} to {to} ({mp}: {source['url']})"]
    if dry_run:
        return {"plan": plan}
    t = Trash(env)
    if to == "claude":
        f = env.claude / "settings.json"
        t.backup(f)
        s = _read_json(f, {})
        s.setdefault("enabledPlugins", {})[pid] = True
        s.setdefault("extraKnownMarketplaces", {}).setdefault(mp, {"source": {"source": "git", "url": source["url"]}})
        _write_json(f, s)
    else:
        f = env.codex / "config.toml"
        t.backup(f)
        f.write_text(_codex_add(f.read_text(encoding="utf-8") if f.exists() else "", pid, mp, source), encoding="utf-8")
    return {"plan": plan, "trash": t.save()}


def delete_plugin(env: Env, pid: str, purge_cache: bool = False, dry_run: bool = True) -> dict:
    """Remove a plugin from Claude's and Codex's config (optionally their downloaded copies too)."""
    _check_plugin(pid)
    name, mp = pid.split("@")
    cl_cfg, cl_inst, cx_cfg = env.claude / "settings.json", env.claude / "plugins" / "installed_plugins.json", env.codex / "config.toml"
    plan = []
    if pid in _read_json(cl_inst, {}).get("plugins", {}):
        plan.append(f"remove {pid} from {cl_inst}")
    if pid in _read_json(cl_cfg, {}).get("enabledPlugins", {}):
        plan.append(f"remove {pid} from {cl_cfg}")
    if cx_cfg.exists() and _toml_block(pid).search(cx_cfg.read_text(encoding="utf-8")):
        plan.append(f"remove [plugins.\"{pid}\"] from {cx_cfg}")
    caches = [p for p in (env.claude / "plugins" / "cache" / mp / name, env.codex / "plugins" / "cache" / mp / name)
              if purge_cache and p.is_dir()]
    plan += [f"move {p} to trash" for p in caches]
    if not plan:
        raise ValueError(f"{pid} is not in Claude or Codex")
    if dry_run:
        return {"plan": plan}
    t = Trash(env)
    for f in (cl_inst, cl_cfg, cx_cfg):
        t.backup(f)
    inst = _read_json(cl_inst, None)
    if inst and pid in inst.get("plugins", {}):
        del inst["plugins"][pid]
        _write_json(cl_inst, inst)
    cfg = _read_json(cl_cfg, None)
    if cfg and pid in cfg.get("enabledPlugins", {}):
        del cfg["enabledPlugins"][pid]
        _write_json(cl_cfg, cfg)
    if cx_cfg.exists():
        cx_cfg.write_text(_toml_block(pid).sub("", cx_cfg.read_text(encoding="utf-8")), encoding="utf-8")
    for p in caches:
        t.move(p)
    return {"plan": plan, "trash": t.save()}


def promote_plugin(env: Env, project: str, pid: str, dry_run: bool = True) -> dict:
    """Move a plugin switched on in a project's .claude/settings.json to the user's settings."""
    _check_plugin(pid)
    proj = Path(project)
    files = [proj / ".claude" / n for n in ("settings.json", "settings.local.json")
             if pid in _read_json(proj / ".claude" / n, {}).get("enabledPlugins", {})]
    if not files:
        raise ValueError(f"{pid} is not in {proj / '.claude'}")
    plan = [f"switch {pid} on in {env.claude / 'settings.json'}"] + [f"remove it from {f}" for f in files]
    if dry_run:
        return {"plan": plan}
    t = Trash(env)
    t.backup(env.claude / "settings.json")
    user = _read_json(env.claude / "settings.json", {})
    user.setdefault("enabledPlugins", {})[pid] = True
    for f in files:
        t.backup(f)
        s = _read_json(f, {})
        mp = pid.split("@")[1]
        if mp in s.get("extraKnownMarketplaces", {}):
            user.setdefault("extraKnownMarketplaces", {}).setdefault(mp, s["extraKnownMarketplaces"][mp])
        del s["enabledPlugins"][pid]
        _write_json(f, s)
    _write_json(env.claude / "settings.json", user)
    return {"plan": plan, "trash": t.save()}


# ---------------------------------------------------------------- export / import

def _skill_files(folder: Path):
    for root, _, files in os.walk(folder):
        for f in files:
            full = Path(root) / f
            yield full, full.relative_to(folder).as_posix()


def _manifest(env: Env) -> dict:
    enabled = _read_json(env.claude / "settings.json", {}).get("enabledPlugins", {})
    installed = _read_json(env.claude / "plugins" / "installed_plugins.json", {}).get("plugins", {})
    return {"version": 1, "marketplaces": _marketplaces(env),
            "claude": {pid: bool(enabled.get(pid, True)) for pid in sorted(set(installed) | set(enabled))},
            "codex": {pid: bool(c.get("enabled", True)) for pid, c in _toml(env.codex / "config.toml").get("plugins", {}).items()}}


def export_bundle(env: Env, folder: str, password: str = "", project_skills: list | None = None) -> dict:
    """One zip (or .hbk with a password): global skills, chosen project skills, plugins.json."""
    out_dir = Path(transfer._check(folder, False))
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen = {}
    for row in scan_skills(env):
        if row["source"] and Path(row["source"]).is_dir():
            chosen[row["name"]] = Path(row["source"])
    notes = []
    for p in project_skills or []:
        src = Path(p)
        if not src.is_dir() or src.parent.name != "skills":
            raise ValueError(f"not a skill folder: {p}")
        if src.name in chosen:
            notes.append(f"skipped project skill {src.name}: a global skill has that name")
        else:
            chosen[_check_name(src.name)] = src
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in sorted(chosen.items()):
            for full, rel in _skill_files(src):
                z.write(full, f"skills/{name}/{rel}")
        z.writestr("plugins.json", json.dumps(_manifest(env), indent=2))
    data = transfer.encrypt(buf.getvalue(), password) if password else buf.getvalue()
    out = out_dir / (PREFIX + time.strftime("%Y%m%d-%H%M%S") + (".hbk" if password else ".zip"))
    out.write_bytes(data)
    m = _manifest(env)
    return {"skills": len(chosen), "plugins": len(set(m["claude"]) | set(m["codex"])), "file": str(out), "notes": notes}


def _newest_bundle(folder: Path) -> Path | None:
    found = [p for ext in ("zip", "hbk") for p in folder.glob(f"{PREFIX}*.{ext}")]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def import_bundle(env: Env, path: str, password: str = "", dry_run: bool = True) -> dict:
    """Restore skills into the store (old copies go to trash), link both tools, and merge plugins.json."""
    p = Path(transfer._check(path, True))
    if p.is_dir():
        p = _newest_bundle(p)
        if p is None:
            raise ValueError("no hooks-skills-*.zip or .hbk in that folder")
    data = p.read_bytes()
    if data.startswith(transfer.MAGIC):
        if not password:
            raise ValueError("this backup is encrypted: enter its password")
        data = transfer.decrypt(data, password)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("not a hooks skills backup") from None
    members = {}
    with z:
        for info in z.infolist():
            top, _, rest = info.filename.partition("/")
            if info.is_dir() or top != "skills":
                continue
            name, _, rel = rest.partition("/")
            target = os.path.abspath(os.path.join(env.store, name, rel))
            if not rel or not NAME.match(name) or os.path.commonpath([os.path.abspath(env.store), target]) != os.path.abspath(env.store):
                raise ValueError(f"unsafe path in backup: {info.filename}")
            members.setdefault(name, []).append((info, target))
        manifest = json.loads(z.read("plugins.json")) if "plugins.json" in z.namelist() else {}
        plan = [f"skill {n}" + (" (replaces the current one)" if (env.store / n).exists() else "") for n in sorted(members)]
        plan += [f"plugin {pid} in {side}" for side in ("claude", "codex") for pid in manifest.get(side, {})]
        if dry_run:
            return {"plan": plan, "file": str(p)}
        t = Trash(env)
        for name, files in members.items():
            if (env.store / name).exists():
                t.move(env.store / name)
            for info, target in files:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            for h in env.homes.values():
                if _kind(h / name) == "dir":
                    t.move(h / name)
                _link(env.store / name, h / name)
    notes = _import_plugins(env, manifest, t)
    return {"plan": plan, "file": str(p), "skills": len(members), "notes": notes, "trash": t.save()}


def _import_plugins(env: Env, manifest: dict, t: Trash) -> list:
    notes, known = [], _marketplaces(env)
    mps = manifest.get("marketplaces", {})

    def usable(pid):
        mp = pid.split("@")[-1]
        src = known.get(mp) or mps.get(mp)
        if not src or src.get("type") != "git":
            notes.append(f"skipped {pid}: marketplace {mp} is local to the other machine or unknown")
            return None
        return src

    if manifest.get("claude"):
        f = env.claude / "settings.json"
        t.backup(f)
        s = _read_json(f, {})
        for pid, on in manifest["claude"].items():
            if _check_plugin(pid) and (src := usable(pid)):
                s.setdefault("enabledPlugins", {})[pid] = on
                s.setdefault("extraKnownMarketplaces", {}).setdefault(pid.split("@")[1], {"source": {"source": "git", "url": src["url"]}})
        _write_json(f, s)
    if manifest.get("codex"):
        f = env.codex / "config.toml"
        t.backup(f)
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        for pid in manifest["codex"]:
            if _check_plugin(pid) and (src := usable(pid)):
                text = _codex_add(text, pid, pid.split("@")[1], src)
        f.write_text(text, encoding="utf-8")
    return notes


# ---------------------------------------------------------------- web entry

def handle(action: str, body: dict, env: Env | None = None) -> dict:
    """Dispatch one web request. Destructive actions run only when body["dry_run"] is false."""
    env = env or Env()
    dry = body.get("dry_run", True) is not False
    if action == "scan":
        return scan(env)
    if action == "sync_skills":
        return {"plan": sync_skills(env, dry)}
    if action == "delete_skill":
        return delete_skill(env, str(body.get("name", "")), dry)
    if action == "promote_skill":
        return promote_skill(env, str(body.get("path", "")), str(body.get("mode", "link")), bool(body.get("overwrite")), dry)
    if action == "add_plugin":
        return add_plugin(env, str(body.get("id", "")), str(body.get("to", "")), dry)
    if action == "delete_plugin":
        return delete_plugin(env, str(body.get("id", "")), bool(body.get("purge_cache")), dry)
    if action == "promote_plugin":
        return promote_plugin(env, str(body.get("project", "")), str(body.get("id", "")), dry)
    if action == "export":
        return export_bundle(env, str(body.get("folder", "")), str(body.get("password", "")), list(body.get("project_skills") or []))
    if action == "import":
        return import_bundle(env, str(body.get("path", "")), str(body.get("password", "")), dry)
    if action == "restore":
        return {"restored": restore(env, str(body.get("bucket", "")))}
    raise ValueError(f"unknown action: {action}")
