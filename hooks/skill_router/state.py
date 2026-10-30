"""On/off switch and stats for the skill picker's always-on hook mode."""

from core.py.json_store import JsonStore, SwitchState
from core.py.paths import data_path


class SkillRouterState(SwitchState):
    path = data_path("skill_router", "state.json")


class SkillRouterStats(JsonStore):
    path = data_path("skill_router", "stats.json")
    defaults = {"used": 0, "fallback": 0, "skipped": 0, "jev_failures": 0}

    def record(self, decision: str):
        self.increment("used" if decision == "use" else "fallback")

    def record_skipped(self):
        self.increment("skipped")

    def record_failure(self):
        self.increment("jev_failures")


_state = SkillRouterState()
_stats = SkillRouterStats()

is_enabled = _state.is_enabled
set_enabled = _state.set_enabled
get_stats = _stats.read
record = _stats.record
record_skipped = _stats.record_skipped
record_failure = _stats.record_failure
