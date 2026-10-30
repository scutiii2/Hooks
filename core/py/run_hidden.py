"""Run a console command with no window, relaying stdin/stdout/exit code.

Launch via pythonw.exe so the hook shows no terminal: pythonw run_hidden.py <cmd> [args...]
"""
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000


def main(argv: list[str]) -> int:
    if not argv:
        return 2
    data = sys.stdin.buffer.read() if sys.stdin else b""
    p = subprocess.run(argv, input=data, capture_output=True, creationflags=CREATE_NO_WINDOW)
    if sys.stdout:
        sys.stdout.buffer.write(p.stdout)
        sys.stdout.flush()
    if sys.stderr:
        sys.stderr.buffer.write(p.stderr)
        sys.stderr.flush()
    return p.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
