"""Base class for small JSON-file-backed state/stats stores."""
import json
import os


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
        for key, val in self.defaults.items():
            if isinstance(val, dict):
                data.setdefault(key, {})
                for sub_key, sub_val in val.items():
                    data[key].setdefault(sub_key, sub_val)
            else:
                data.setdefault(key, val)
        return data

    def write(self, data: dict):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
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
