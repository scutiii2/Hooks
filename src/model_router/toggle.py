"""On/off switch and status check for the model router.

Usage:
    python -m src.model_router.toggle on
    python -m src.model_router.toggle off
    python -m src.model_router.toggle status
"""
import sys

from . import state
from ..core import provider
from ..cli.toggle_cli import ToggleCLI


class ModelRouterToggle(ToggleCLI):
    usage = "Usage: python -m src.model_router.toggle on|off|status"

    def on_message(self):
        name = provider._provider_name()
        via = "via LayaModel, falling back to Jev (TypeSafe API) if it is unreachable" \
            if name == "laya" else "via Jev (TypeSafe API)"
        return (f"Router ON. Messages now get classified {via}.\n"
                "Turn OFF for anything private: python -m src.model_router.toggle off")

    def off_message(self):
        return "Router OFF."

    def is_enabled(self):
        return state.is_enabled()

    def set_enabled(self, value):
        state.set_enabled(value)

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
