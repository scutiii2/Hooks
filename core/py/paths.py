"""Hooks root and the folders under it. Dot-folders are gitignored, created on first write."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOKS = os.path.join(ROOT, "hooks")
DATA = os.path.join(ROOT, ".data")  # data the hooks create: state, stats, logs
MEMORY = os.path.join(ROOT, ".memory")  # material used to improve a hook: labeled examples


def data_path(hook: str, filename: str) -> str:
    return os.path.join(DATA, hook, filename)


def memory_path(hook: str, filename: str) -> str:
    return os.path.join(MEMORY, hook, filename)
