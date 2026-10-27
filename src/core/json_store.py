"""Base class for small JSON-file-backed state/stats stores."""
import json
import os


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
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def update(self, **changes):
        data = self.read()
        data.update(changes)
        self.write(data)
        return data

    def increment(self, key: str):
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
