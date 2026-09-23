"""On/off switch and stats for the skill picker's always-on hook mode."""
import os

from ..core.json_store import JsonStore

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SkillRouterState(JsonStore):
    path = os.path.join(ROOT, "skill_router_state.json")
    defaults = {"enabled": False}

    def is_enabled(self) -> bool:
        return bool(self.read().get("enabled", False))

    def set_enabled(self, value: bool):
        self.write({"enabled": bool(value)})


class SkillRouterStats(JsonStore):
    path = os.path.join(ROOT, "skill_router_stats.json")
    defaults = {"used": 0, "fallback": 0, "jev_failures": 0, "jev_cost_usd": 0.0}

    def record(self, decision: str, cost_usd: float):
        stats = self.read()
        stats["used" if decision == "use" else "fallback"] += 1
        stats["jev_cost_usd"] += cost_usd
        self.write(stats)

    def record_failure(self):
        stats = self.read()
        stats["jev_failures"] += 1
        self.write(stats)


_state = SkillRouterState()
_stats = SkillRouterStats()

is_enabled = _state.is_enabled
set_enabled = _state.set_enabled
get_stats = _stats.read
record = _stats.record
record_failure = _stats.record_failure
