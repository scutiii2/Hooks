"""Pick a hook or tool by its short name; this is what run.bat starts.

    run.bat                          menu: pick a number, then type the arguments
    run.bat list                     the short names
    run.bat model_router status      same as: python -m hooks.model_router.toggle status
    run.bat hooks.x.y arg            a full module path still works
"""
import subprocess
import sys

from ..paths import ROOT

# name: (python arguments, usage shown after the name, one-line purpose)
COMMANDS = {
    "model_router": (["-m", "hooks.model_router.toggle"], "on|off|status", "model router switch and stats"),
    "skill_router": (["-m", "hooks.skill_router.toggle"], "on|off|status", "skill router switch and stats"),
    "skill_pick": (["-m", "hooks.skill_router.pick"], '"request text"', "ask the skill router once, no toggle needed"),
    "te_patch": (["hooks/token_economizer_patch/te_patch.py"], "status|apply|ensure|on|off|update|rebuild|refresh",
                 "TokenEconomizer plugin and our patch"),
    "source_of_truth": (["hooks/source_of_truth/source_of_truth.py"], "[project dir]",
                        "make AGENTS.md the one source for a project"),
    "web": (["-m", "core.py.tools.web"], "[--port 8765]", "web view of the logs"),
    "watch": (["-m", "core.py.tools.watch_decisions"], "[--last N]", "live decisions in the terminal"),
    "calibrate": (["-m", "core.py.tools.calibrate"], "[--since EPOCH]", "follow rate per confidence bucket"),
    "label": (["-m", "core.py.tools.label_review"], "model|skill", "review and correct logged predictions"),
    "export": (["-m", "core.py.tools.export_training_data"], "model|skill", "labeled data to training JSONL"),
    "settings": (["-m", "core.py.tools.manage_hooks"], "add|remove [settings.json]", "install or remove hooks in Claude settings"),
}


def resolve(argv: list[str]) -> list[str] | None:
    """Python arguments for `argv`, or None when argv is empty. Unknown names run as module paths."""
    if not argv:
        return None
    name, rest = argv[0], argv[1:]
    if name in COMMANDS:
        return COMMANDS[name][0] + rest
    if "." not in name:
        raise SystemExit(f"Unknown name '{name}'. Names:\n{listing()}")
    return ["-m", name, *rest]


def listing() -> str:
    width = max(map(len, COMMANDS))
    return "\n".join(f"  {name:<{width}}  {usage}\n  {'':<{width}}  {purpose}" for name, (_, usage, purpose) in COMMANDS.items())


def menu() -> list[str] | None:
    names = list(COMMANDS)
    for i, name in enumerate(names, 1):
        _, usage, purpose = COMMANDS[name]
        print(f"{i:>2}. {name:<16} {purpose}  {usage}")
    try:
        choice = input("\nNumber or name (Enter to quit): ").strip("﻿ \t")
        if not choice:
            return None
        name = names[int(choice) - 1] if choice.isdigit() and 0 < int(choice) <= len(names) else choice
        extra = input(f"Arguments for {name}: ").split()
    except (EOFError, KeyboardInterrupt):
        return None
    return resolve([name, *extra])


def main(argv: list[str]) -> int:
    if argv == ["list"] or argv == ["--help"]:
        print("run.bat <name> [args]\n" + listing())
        return 0
    args = resolve(argv) if argv else menu()
    if args is None:
        return 0
    return subprocess.call([sys.executable, *args], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
