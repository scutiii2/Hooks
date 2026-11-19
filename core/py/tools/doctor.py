"""Health check: is this machine set up so the hooks can run?

    python -m core.py.tools.doctor           check only
    python -m core.py.tools.doctor --fix     then offer to fix what it can (asks Y/N for each; --yes skips the question)

Checks Python, the .venv, node, a writable .data folder, the Claude and Codex CLIs with TokenEconomizer, and that every hook in the Claude and Codex
config points at files that exist and includes the hooks `manage_hooks add` installs. Prints one
line per check and exits 1 when something fails. Without --fix it changes nothing. --fix can create the
.venv, install a missing CLI or TokenEconomizer, and install the hooks of this folder in Claude and Codex; it never edits or removes other hooks.
"""
import json
import os
import importlib.util
import re
import shutil
import subprocess
import sys
import venv

from ..paths import DATA, ROOT
from . import manage_hooks, transfer

OK, WARN, FAIL = "ok  ", "warn", "FAIL"
FILE_WORD = re.compile(r"\.(exe|py|js|json)$", re.I)


def venv_python() -> str:
    return os.path.join(ROOT, ".venv", "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")


words = manage_hooks.command_words


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


def te_patch():
    """The TokenEconomizer helper, loaded by path: it is a script, not part of a package."""
    path = os.path.join(ROOT, "hooks", "token_economizer_patch", "te_patch.py")
    spec = importlib.util.spec_from_file_location("te_patch_doctor", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_te() -> list[tuple[str, str, str]]:
    try:
        return [(OK if lvl == "ok" else WARN, text, fix) for lvl, text, fix in te_patch().health()]
    except Exception as e:  # a broken helper must not stop the other checks
        return [(WARN, f"TokenEconomizer helper could not run: {type(e).__name__}: {e}", "")]


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
    checks.append((OK, "cryptography: installed (backups use AES-GCM)") if transfer._gcm()
                  else (WARN, "cryptography not installed: encrypted backups use the home-built cipher (pip install cryptography)"))
    checks.append((OK, f".data writable: {DATA}") if writable(DATA) else (FAIL, f"cannot write {DATA}"))
    checks += check_config("claude", manage_hooks.CLAUDE_TARGET)
    checks += check_config("codex", manage_hooks.CODEX_TARGET)
    checks += [(level, text) for level, text, _ in check_te()]
    return checks


def fixes() -> list[tuple[str, callable]]:
    """(what it does, how) for each problem this tool can repair on its own."""
    todo = []
    if not os.path.exists(venv_python()):
        todo.append(("create .venv", lambda: venv.create(os.path.join(ROOT, ".venv"), with_pip=True)))
    if not transfer._gcm():
        todo.append(("install the cryptography package (AES-GCM for encrypted backups)",
                     lambda: subprocess.run([sys.executable, "-m", "pip", "install", "cryptography"], check=False)))
    for host, target in (("claude", manage_hooks.CLAUDE_TARGET), ("codex", manage_hooks.CODEX_TARGET)):
        if any("not installed" in t or "does not exist" in t for level, t in check_config(host, target) if level == WARN):
            todo.append((f"install the hooks of this folder in {host} ({target})", lambda h=host, t=target: manage_hooks.add(t, h)))
    for level, text, fix in check_te():
        host = text.split(":")[0]
        if fix == "cli":
            todo.append((f"install the {host} CLI with its official installer", lambda h=host: te_patch().install_cli([h], yes=True)))
        elif fix == "ensure":
            mod = te_patch()
            todo.append((f"install TokenEconomizer for {host}", lambda h=host: print(chr(10).join(mod.ensure([x for x in mod.HOSTS if x.name == h])))))
    return todo


def show(checks) -> int:
    for level, text in checks:
        print(f"[{level}] {text}")
    return 1 if any(level == FAIL for level, _ in checks) else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    code = show(run())
    if "--fix" not in argv:
        return code
    todo = fixes()
    if not todo:
        print("\nNothing to fix automatically." if code == 0 else "\nNothing here can be fixed automatically; see the lines above.")
        return code
    for what, fix in todo:
        if "--yes" not in argv and input(f"\n{what}? [y/N] ").strip().lower() != "y":
            continue
        fix()
    print()
    return show(run())


if __name__ == "__main__":
    sys.exit(main())
