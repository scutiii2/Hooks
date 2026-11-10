#!/usr/bin/env python3
"""TokenEconomizerPatch: install TokenEconomizer for Claude Code and Codex, then keep our patch on it.

A TokenEconomizer update installs a fresh copy and drops local edits. Our edits live here as
`history-bootstrap.patch` (made against upstream `tokeneconomizer/`). For each host (Claude
Code, Codex) this script installs the plugin when it is missing, then applies the patch.

    te_patch.py              hook mode (SessionStart on either host): never blocks, fails open
    te_patch.py ensure       install what is missing, then apply, in the foreground
    te_patch.py apply        apply to every installed copy now
    te_patch.py on|off [claude|codex]   enable/disable the plugin (and apply/remove the patch)
    te_patch.py status       enabled flag and patch state per host
    te_patch.py update [claude|codex]   remove patch, update from the marketplace, re-apply
    te_patch.py rebuild [claude|codex]  uninstall, reinstall from the marketplace, apply the patch
    te_patch.py refresh      rebuild the patch from the git diff in the Claude marketplace clone

On/off uses each host's own flag: `enabledPlugins` in Claude's settings.json, and
`[plugins."tokeneconomizer@tokeneconomizer"] enabled` in Codex's config.toml. A host whose flag
is false is left alone: no install, no patch.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK = HERE / ".ensure.lock"
LAST_NOTE = HERE.parents[1] / ".data" / "token_economizer_patch" / "last_note.txt"  # a note shows once, not every session
KEY = "tokeneconomizer@tokeneconomizer"
SOURCE = "microsoft/TokenEconomizer"
CLAUDE = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
CODEX = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
CLONE = CLAUDE / "plugins" / "marketplaces" / "tokeneconomizer"


NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # under pythonw a console child (git) would open a terminal window


def run(*cmd: str, cwd: Path | None = None, timeout: int = 300) -> bool:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class Host:
    """One agent CLI that can hold the plugin. Subclasses say where and how."""
    name = ""

    def targets(self) -> list[tuple[Path, str]]:
        """[(dir to run git apply in, --directory prefix)] for each installed copy."""
        raise NotImplementedError

    def enabled(self) -> bool: raise NotImplementedError
    def set_enabled(self, value: bool) -> None: raise NotImplementedError
    def install(self) -> bool: raise NotImplementedError
    def update(self) -> bool: raise NotImplementedError
    def uninstall(self) -> bool: raise NotImplementedError

    def installed(self) -> bool:
        return bool(self.targets())


class ClaudeHost(Host):
    name = "claude"
    settings = CLAUDE / "settings.json"
    registry = CLAUDE / "plugins" / "installed_plugins.json"

    @staticmethod
    def _json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def targets(self):
        entries = self._json(self.registry).get("plugins", {}).get(KEY, [])
        paths = (Path(e["installPath"]) for e in entries if "installPath" in e)
        # the installed bundle keeps the package under lib/
        return [(p, "lib") for p in paths if p.is_dir()]

    def enabled(self):
        return bool(self._json(self.settings).get("enabledPlugins", {}).get(KEY))

    def set_enabled(self, value):
        data = self._json(self.settings)
        if not data:
            raise RuntimeError(f"cannot read {self.settings}; not touching it")
        data.setdefault("enabledPlugins", {})[KEY] = value
        tmp = self.settings.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.settings)

    def install(self):
        run("claude", "plugin", "marketplace", "add", SOURCE)  # fails harmlessly when already added
        return run("claude", "plugin", "install", KEY)

    def uninstall(self):
        return run("claude", "plugin", "uninstall", "--keep-data", KEY)

    def update(self):
        run("claude", "plugin", "marketplace", "update", "tokeneconomizer")
        return run("claude", "plugin", "update", KEY)


class CodexHost(Host):
    name = "codex"
    config = CODEX / "config.toml"
    section = f'[plugins."{KEY}"]'

    def targets(self):
        out = []
        for p in sorted((CODEX / "plugins" / "cache" / "tokeneconomizer" / "tokeneconomizer").glob("*")):
            if (p / "lib" / "tokeneconomizer").is_dir():
                out.append((p, "lib"))
            else:
                # Codex drops the lib symlink; the plugin then imports the package from the
                # marketplace checkout. shortcut: only a checkout that Codex keeps under its home is found.
                for c in CODEX.glob("**/marketplaces/tokeneconomizer"):
                    if (c / "tokeneconomizer").is_dir():
                        out.append((c, ""))
                        break
        return out

    def _text(self) -> str:
        try:
            return self.config.read_text(encoding="utf-8")
        except OSError:
            return ""

    def _section(self, text: str):
        return re.search(re.escape(self.section) + r"[^\[]*", text)

    def enabled(self):
        m = self._section(self._text())
        return not (m and re.search(r"^\s*enabled\s*=\s*false", m.group(0), re.M))  # absent = on

    def set_enabled(self, value):
        text, flag = self._text(), f"enabled = {str(value).lower()}"
        m = self._section(text)
        if m is None:
            text = text.rstrip("\n") + f"\n\n{self.section}\n{flag}\n"
        elif re.search(r"^\s*enabled\s*=", m.group(0), re.M):
            new = re.sub(r"^(\s*)enabled\s*=.*$", rf"\g<1>{flag}", m.group(0), flags=re.M)
            text = text[:m.start()] + new + text[m.end():]
        else:
            head = self.section + "\n"
            text = text[:m.start()] + head + flag + "\n" + m.group(0)[len(head):] + text[m.end():]
        self.config.write_text(text, encoding="utf-8")

    def install(self):
        run("codex", "plugin", "marketplace", "add", SOURCE)
        return run("codex", "plugin", "add", KEY)

    def uninstall(self):
        return run("codex", "plugin", "remove", KEY)

    def update(self):
        return run("codex", "plugin", "marketplace", "upgrade", "tokeneconomizer")


HOSTS = [ClaudeHost(), CodexHost()]


def patches() -> list[Path]:
    """One patch per upstream version we follow, newest first; the one that fits an install wins."""
    return sorted(HERE.glob("history-bootstrap*.patch"), key=lambda p: p.stat().st_mtime, reverse=True)


def _git_apply(target: Path, prefix: str, patch: Path, *flags: str) -> bool:
    cmd = ["git", "apply", "--whitespace=nowarn", *([f"--directory={prefix}"] if prefix else []), *flags, str(patch)]
    return run(*cmd, cwd=target)


def state(target: Path, prefix: str) -> tuple[str, Path | None]:
    """(applied | missing | conflict, the patch that fits). Conflict: upstream changed the patched code."""
    found = patches()
    for p in found:
        if _git_apply(target, prefix, p, "--reverse", "--check"):
            return "applied", p
    for p in found:
        if _git_apply(target, prefix, p, "--check"):
            return "missing", p
    return "conflict", None


def apply(target: Path, prefix: str) -> str:
    s, p = state(target, prefix)
    return "applied now" if s == "missing" and _git_apply(target, prefix, p) else s


def remove(target: Path, prefix: str) -> str:
    s, p = state(target, prefix)
    if s == "applied" and _git_apply(target, prefix, p, "--reverse"):
        return "removed"
    return "not applied" if s == "missing" else s


def ensure(hosts=HOSTS) -> list[str]:
    """Install missing plugins on enabled hosts, then patch every installed copy."""
    notes = []
    for h in hosts:
        if not h.enabled():
            continue
        if not h.installed():
            notes.append(f"TokenEconomizer {'installed' if h.install() else 'install FAILED'} for {h.name}.")
        if not h.installed():
            continue
        for t, prefix in h.targets():
            r = apply(t, prefix)
            if r == "applied now":
                notes.append(f"History patch applied to {h.name} ({t.name}).")
            elif r == "conflict":
                notes.append(f"Update conflicts with the history patch for {h.name} ({t.name}); "
                             "bootstrap is off there until you run te_patch.py update " + h.name + " (or off " + h.name + ").")
    return notes


def refresh() -> None:
    """Rebuild the patch from the clone's working-tree changes (new files included)."""
    def git(*a: str) -> bytes:
        return subprocess.run(["git", *a], cwd=CLONE, capture_output=True, check=True, creationflags=NO_WINDOW).stdout
    new = [f for f in git("ls-files", "--others", "--exclude-standard", "tokeneconomizer").decode().split("\n") if f]
    if new:
        git("add", "-N", *new)
    try:
        (HERE / "history-bootstrap.patch").write_bytes(git("diff", "HEAD", "--binary", "--", "tokeneconomizer"))
    finally:
        if new:
            git("reset", "-q", "--", *new)


def _needs_install() -> bool:
    return any(h.enabled() and not h.installed() for h in HOSTS)


def log_run(started: float, record: dict) -> None:
    """Run log in .data/token_economizer_patch/runs.jsonl; this file runs by path, so find core/ first."""
    try:
        sys.path.insert(0, str(HERE.parents[1]))
        from core.py.runlog import log_run as write
        write("token_economizer_patch", {"event": "SessionStart", **record}, started)
    except Exception:
        pass


def hook() -> int:
    """SessionStart: patch inline; run a missing install detached, since it is slow."""
    started, record = time.time(), {"outcome": "error"}
    try:
        try:  # the session id ties this run to a chat; a hand run has a tty and no payload
            sid = None if sys.stdin is None or sys.stdin.isatty() else json.load(sys.stdin).get("session_id")
        except (ValueError, OSError):  # no payload, or stdin closed
            sid = None
        if not patches():
            record = {"outcome": "no_patch"}
            return 0
        notes = []
        if _needs_install():
            if not LOCK.exists() or time.time() - LOCK.stat().st_mtime > 900:
                LOCK.touch()
                flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED | NEW_GROUP
                subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "ensure"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, creationflags=flags)
                notes.append("TokenEconomizer is missing on a host; installing it in the background.")
        notes += ensure([h for h in HOSTS if h.installed()])
        text = " ".join(notes)
        seen = LAST_NOTE.read_text(encoding="utf-8") if LAST_NOTE.exists() else ""
        if text and text == seen:
            notes = []  # same note as last session: logged, not shown again
        elif text or seen:
            LAST_NOTE.parent.mkdir(parents=True, exist_ok=True)
            LAST_NOTE.write_text(text, encoding="utf-8")
        record = {"session_id": sid, "outcome": "notes" if notes else ("repeat" if text else "nothing"),
                  "notes": len(notes), "note": text[:300]}
        if notes:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                     "additionalContext": " ".join(notes)}}))
    except Exception:
        pass
    finally:
        log_run(started, record)
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    if not cmd:
        return hook()
    chosen = [h for h in HOSTS if h.name in argv[1:]] or HOSTS
    if cmd == "ensure":
        try:
            print("\n".join(ensure()) or "nothing to do")
        finally:
            LOCK.unlink(missing_ok=True)
    elif cmd == "apply":
        for h in chosen:
            for t, p in h.targets():
                print(f"{h.name} {t}: {apply(t, p)}")
    elif cmd in ("on", "off"):
        for h in chosen:
            h.set_enabled(cmd == "on")
            for t, p in h.targets():
                print(f"{h.name} {t}: {apply(t, p) if cmd == 'on' else remove(t, p)}")
            print(f"{h.name} enabled: {h.enabled()}")
        if cmd == "on":
            print("\n".join(ensure(chosen)))
    elif cmd == "status":
        for h in chosen:
            print(f"{h.name}: enabled={h.enabled()} installed={h.installed()}")
            for t, p in h.targets():
                s, pf = state(t, p)
                print(f"  {t}: {s}" + (f" ({pf.name})" if pf else ""))
    elif cmd == "rebuild":
        for h in chosen:  # clean reinstall: uninstall, then ensure() installs and patches
            for tg, p in h.targets():
                remove(tg, p)
            print(f"{h.name} uninstall {'ok' if h.uninstall() else 'FAILED'}")
            print("\n".join(ensure([h])) or "nothing to do")
    elif cmd == "update":
        for h in chosen:
            for tg, p in h.targets():  # a clean tree lets the host update it
                remove(tg, p)
            print(f"{h.name} update {'ok' if h.update() else 'FAILED'}")
            print("\n".join(ensure([h])) or "patch already in place")
    elif cmd == "refresh":
        refresh()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
