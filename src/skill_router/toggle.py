"""On/off switch and status check for the always-on skill picker.

Usage:
    python -m src.skill_router.toggle on
    python -m src.skill_router.toggle off
    python -m src.skill_router.toggle status
"""
import sys

from . import state
from ..cli.toggle_cli import ToggleCLI


class SkillRouterToggle(ToggleCLI):
    usage = "Usage: python -m src.skill_router.toggle on|off|status"
    state = state

    def on_message(self):
        return (f"Skill picker ON for every message. Requests now get classified {self.via}.\n"
                "Turn OFF for anything private: python -m src.skill_router.toggle off")

    def off_message(self):
        return "Skill picker (always-on mode) OFF. Manual `pick.py` still works."

    def print_status(self):
        enabled = state.is_enabled()
        stats = state.get_stats()
        print(f"Always-on skill picker: {'ON' if enabled else 'OFF'}")
        print(f"Used Jev's pick: {stats['used']}")
        print(f"Fell back to normal matching: {stats['fallback']}")
        print(f"Jev failures: {stats['jev_failures']}")


if __name__ == "__main__":
    SkillRouterToggle().run(sys.argv)
