"""On/off switch and status check for the model router.

Usage:
    python -m hooks.model_router.toggle on
    python -m hooks.model_router.toggle off
    python -m hooks.model_router.toggle status
"""
import sys

from . import state
from core.py.toggle_cli import ToggleCLI


class ModelRouterToggle(ToggleCLI):
    usage = "Usage: python -m hooks.model_router.toggle on|off|status"
    state = state

    def on_message(self):
        return (f"Router ON. Messages now get classified {self.via}.\n"
                "Turn OFF for anything private: python -m hooks.model_router.toggle off")

    def print_status(self):
        enabled = state.is_enabled()
        stats = state.get_stats()
        print(f"Router: {'ON' if enabled else 'OFF'}")
        print("Messages by size:")
        for size, count in stats["counts"].items():
            print(f"  {size:10s} {count}")
        print(f"Handled directly (no routing): {stats['handled_by_me']}")
        print(f"Jev calls: {stats['jev_calls']}  (failures: {stats['jev_failures']})")


if __name__ == "__main__":
    ModelRouterToggle().run(sys.argv)
