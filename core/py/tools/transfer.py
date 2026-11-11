"""Copy the hooks' local state to a folder and back: `.data/` (logs, state, stats) and `.memory/` (labeled examples).

The folder gets `data/` and `.memory`'s copy `memory/`. Import overwrites same-named files and keeps the rest.
"""
import os
import shutil
import subprocess
import sys

from .. import paths

PARTS = (("data", "DATA"), ("memory", "MEMORY"))  # folder name in the export, attribute of paths


def _copy(src: str, dst: str) -> int:
    """Copy every file under src into dst, overwriting; return the file count."""
    count = 0
    for root, _, files in os.walk(src):
        target = os.path.join(dst, os.path.relpath(root, src))
        os.makedirs(target, exist_ok=True)
        for name in files:
            shutil.copy2(os.path.join(root, name), os.path.join(target, name))
            count += 1
    return count


def _check(folder: str, must_exist: bool) -> str:
    folder = folder.strip().strip("\"'")
    if not folder:
        raise ValueError("pick a folder first")
    folder = os.path.abspath(folder)
    if must_exist and not os.path.isdir(folder):
        raise ValueError(f"folder not found: {folder}")
    return folder


def export_to(folder: str) -> dict:
    folder = _check(folder, False)
    counts = {}
    for name, attr in PARTS:
        src = getattr(paths, attr)
        counts[name] = _copy(src, os.path.join(folder, name)) if os.path.isdir(src) else 0
    return counts


def import_from(folder: str) -> dict:
    folder = _check(folder, True)
    if not any(os.path.isdir(os.path.join(folder, n)) for n, _ in PARTS):
        raise ValueError("no data/ or memory/ folder in there: not a hooks export")
    counts = {}
    for name, attr in PARTS:
        src = os.path.join(folder, name)
        counts[name] = _copy(src, getattr(paths, attr)) if os.path.isdir(src) else 0
    return counts


_DIALOG = ("import tkinter as t, tkinter.filedialog as f; r = t.Tk(); r.withdraw(); r.attributes('-topmost', True); "
           "print(f.askdirectory(title='Select folder'))")


def pick_folder() -> str:
    """Native folder dialog on the machine running this server (it is localhost only); '' when cancelled."""
    done = subprocess.run([sys.executable, "-c", _DIALOG], capture_output=True, text=True, timeout=300)
    return os.path.normpath(done.stdout.strip()) if done.stdout.strip() else ""
