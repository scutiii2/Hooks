"""Run a router module from any working directory.

    python core/py/run_hook.py hooks.model_router.hook

`python -m hooks...` only finds `hooks` when the current folder is the project root, and
the hooks run in whatever folder the Claude Code session is in. This puts the project
root (found from this file's location, so it survives a move) on the path first.
"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
module = sys.argv.pop(1)
runpy.run_module(module, run_name="__main__", alter_sys=True)
