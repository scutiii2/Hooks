"""Health check: is this machine set up so the hooks can run?

    python -m core.py.tools.doctor

Checks Python, the .venv, node, a writable .data folder, and that every hook in the Claude and Codex
config points at files that exist and includes the hooks `manage_hooks add` installs. Prints one
line per check and exits 1 when something fails. It changes nothing.
"""
import json
import os
import re
import shlex
import shutil
import sys

from ..paths import DATA, ROOT
from . import manage_hooks

OK, WARN, FAIL = "ok  ", "warn", "FAIL"
FILE_WORD = re.compile(r"\.(exe|py|js|json)$", re.I)


def venv_python() -> str:
    return os.path.join(ROOT, ".venv", "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")


def words(handler: dict) -> list[str]:
    """Every word of a hook command, with its args; a Codex command is one string."""
    try:
        head = shlex.split(handler.get("command", ""), posix=False)
    except ValueError:
        head = [handler.get("command", "")]
    return [w.strip("\"'") for w in [*head, *map(str, handler.get("args", []))]]


def handlers(config: dict):
    for event, groups in config.get("hooks", {}).items():
        for group in groups:
            for h in group.get("hooks", []):
                yield event, h


def check_config(host: str, target: str) -> list[tuple[str, str]]:
    if not os.path.exists(target):
        return [(WARN, f"{host}: {target} does not exist (run: manage_hooks add{' --host codex' if host == 'codex' else ''})")]
    try:
        with open(target, encoding="utf-8") as f:
            config = json.loads(f.read().strip() or "{}")
    except ValueError as e:
        return [(FAIL, f"{host}: {target} is not valid JSON ({e})")]
    out, missing = [], set()
    for _, h in handlers(config):
        for w in words(h):
            if FILE_WORD.search(w) and (os.path.isabs(w) or ":" in w[:2]) and not os.path.exists(w):
                missing.add(w)
    out += [(FAIL, f"{host}: hook points at a missing file: {w}") for w in sorted(missing)]
    installed = {manage_hooks._key(h) for _, h in handlers(config)}
    absent = [e for e, _, hs in manage_hooks.GROUPS[host] for h in hs if manage_hooks._key(h) not in installed]
    if absent:
        out.append((WARN, f"{host}: {len(absent)} hook(s) from `manage_hooks add` not installed ({', '.join(sorted(set(absent)))})"))
    if not out:
        out.append((OK, f"{host}: {sum(1 for _ in handlers(config))} hooks, all files exist"))
    return out


def writable(folder: str) -> bool:
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".doctor")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def run() -> list[tuple[str, str]]:
    v = sys.version_info
    checks = [(OK if v >= (3, 11) else FAIL, f"python {v.major}.{v.minor}.{v.micro} (3.11+ needed)")]
    checks.append((OK, f"venv: {venv_python()}") if os.path.exists(venv_python())
                  else (FAIL, f"no .venv: run run.bat (or python -m venv .venv) in {ROOT}"))
    checks.append((OK, f"node: {shutil.which('node')}") if shutil.which("node")
                  else (WARN, "node not on PATH: coding_rules and noise_filter need it"))
    checks.append((OK, f".data writable: {DATA}") if writable(DATA) else (FAIL, f"cannot write {DATA}"))
    checks += check_config("claude", manage_hooks.CLAUDE_TARGET)
    checks += check_config("codex", manage_hooks.CODEX_TARGET)
    return checks


def main() -> int:
    checks = run()
    for level, text in checks:
        print(f"[{level}] {text}")
    return 1 if any(level == FAIL for level, _ in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
