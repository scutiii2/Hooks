"""Base class for small JSON-file-backed state/stats stores."""
import contextlib
import json
import os
import time


def merge_defaults(data: dict, defaults: dict) -> dict:
    """Fill keys missing from `data` (one level deep into dict values) from `defaults`."""
    for key, val in defaults.items():
        if isinstance(val, dict):
            data.setdefault(key, {})
            for sub_key, sub_val in val.items():
                data[key].setdefault(sub_key, sub_val)
        else:
            data.setdefault(key, val)
    return data


class JsonStore:
    """Subclass and set `path` and `defaults` (a dict).

    Handles read-with-fallback, atomic write, and default-key backfill.
    """

    path: str = ""
    defaults: dict = {}

    def read(self) -> dict:
        if not os.path.exists(self.path):
            return dict(self.defaults)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return dict(self.defaults)
        return merge_defaults(data, self.defaults)

    def write(self, data: dict):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.{os.getpid()}.tmp"  # per-process, so concurrent writers never share a temp file
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    @contextlib.contextmanager
    def _locked(self, wait: float = 2.0):
        """Exclusive lock via O_EXCL lockfile, so overlapping read-modify-writes don't lose updates.
        shortcut: a lock older than `wait` is treated as stale and taken over; upgrade to msvcrt/fcntl if that bites."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        lock = self.path + ".lock"
        deadline = time.time() + wait
        while True:
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except (FileExistsError, PermissionError):  # Windows reports a lock being deleted as PermissionError
                if time.time() > deadline:
                    break
                time.sleep(0.01)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                os.remove(lock)

    def increment(self, key: str):
        with self._locked():
            stats = self.read()
            stats[key] += 1
            self.write(stats)


class SwitchState(JsonStore):
    """On/off switch persisted as {"enabled": bool}; off until switched on."""

    defaults = {"enabled": False}

    def is_enabled(self) -> bool:
        return bool(self.read().get("enabled", False))

    def set_enabled(self, value: bool):
        self.write({"enabled": bool(value)})
