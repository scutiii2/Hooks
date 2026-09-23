"""On/off switch and status check for the always-on skill picker.

Usage:
    python -m router.skill_router.toggle on
    python -m router.skill_router.toggle off
    python -m router.skill_router.toggle status
"""
import sys

from . import state
from ..core import provider
from ..cli.toggle_cli import ToggleCLI


class SkillRouterToggle(ToggleCLI):
    usage = "Usage: python -m router.skill_router.toggle on|off|status"

    def on_message(self):
        name = provider._provider_name()
        via = "locally via Laya, no network calls" if name == "laya" \
            else "Jev (OpenRouter/Vercel AI Gateway)"
        return (f"Skill picker ON for every message. Requests now get classified {via}.\n"
                "Turn OFF for anything private: python -m router.skill_router.toggle off")

    def off_message(self):
        return "Skill picker (always-on mode) OFF. Manual `pick.py` still works."

    def is_enabled(self):
        return state.is_enabled()

    def set_enabled(self, value):
        state.set_enabled(value)

    def print_status(self):
        enabled = state.is_enabled()
        stats = state.get_stats()
        print(f"Always-on skill picker: {'ON' if enabled else 'OFF'}")
        print(f"Used Jev's pick: {stats['used']}")
        print(f"Fell back to normal matching: {stats['fallback']}")
        print(f"Jev failures: {stats['jev_failures']}")
        print(f"Jev cost so far: ${stats['jev_cost_usd']:.6f}")


if __name__ == "__main__":
    SkillRouterToggle().run(sys.argv)
