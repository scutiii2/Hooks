"""Base class for on/off/status CLI switches."""
import sys


class ToggleCLI:
    """Subclass and set `usage`, `on_message`, `off_message`, and implement
    `print_status()`. `state` is the router's state module (is_enabled / set_enabled)."""

    usage = "Usage: <script> on|off|status"
    state = None
    via = "via Jev (TypeSafe API)"

    def print_status(self):
        raise NotImplementedError

    def on_message(self) -> str:
        return "Router ON."

    def off_message(self) -> str:
        return "Router OFF."

    def run(self, argv):
        if len(argv) != 2 or argv[1] not in ("on", "off", "status"):
            print(self.usage)
            sys.exit(1)

        cmd = argv[1]
        if cmd == "on":
            self.state.set_enabled(True)
            print(self.on_message())
        elif cmd == "off":
            self.state.set_enabled(False)
            print(self.off_message())
        elif cmd == "status":
            self.print_status()
