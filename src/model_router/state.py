"""On/off switch and usage stats for the model-size router."""
import os

from ..core.json_store import JsonStore, SwitchState
from ..core.paths import ROOT


class RouterState(SwitchState):
    path = os.path.join(ROOT, "data", "state", "router_state.json")


class RouterStats(JsonStore):
    path = os.path.join(ROOT, "data", "stats", "router_stats.json")
    defaults = {
        "counts": {"tiny": 0, "everyday": 0, "large": 0, "hardest": 0},
        "handled_by_me": 0,
        "jev_calls": 0,
        "jev_failures": 0,
    }

    def record_classification(self, size: str):
        stats = self.read()
        stats["counts"][size] = stats["counts"].get(size, 0) + 1
        stats["jev_calls"] += 1
        self.write(stats)

    def record_jev_failure(self):
        self.increment("jev_failures")

    def record_handled_by_me(self):
        self.increment("handled_by_me")


# Module-level singletons — same call sites as before (state.is_enabled(), etc).
_state = RouterState()
_stats = RouterStats()

is_enabled = _state.is_enabled
set_enabled = _state.set_enabled
get_stats = _stats.read
record_classification = _stats.record_classification
record_jev_failure = _stats.record_jev_failure
record_handled_by_me = _stats.record_handled_by_me
