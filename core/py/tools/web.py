"""Local web page. Home runs the CLI commands; Logs shows .data/<hook>/*.jsonl, refreshed live.

    python -m core.py.tools.web [--port 8765]

Listens on 127.0.0.1 only. Prompt text stays out of the responses unless the page asks for it.
Decision records get the same followed / pending / ignored? status as the terminal watcher.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ..paths import DATA, ROOT
from ..training_log import followed_log
from .cli import COMMANDS, resolve as resolve_command
from .watch_decisions import IGNORE_AFTER_SECONDS, matching_decision

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web.html")
NAME = re.compile(r"[\w-]+")
CHUNK = 512 * 1024  # a poll reads only this much from the end of a log
MAX_ROWS = 500
NOT_HERE = {"web", "watch", "label"}  # this server, a live terminal view, an interactive review
RUN_TIMEOUT = 120
HOSTS = ("127.0.0.1", "localhost")  # refuse other Host headers: a rebinding page must not read the logs


def list_logs() -> list[dict]:
    out = []
    for hook in sorted(os.listdir(DATA)) if os.path.isdir(DATA) else []:
        folder = os.path.join(DATA, hook)
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            if name.endswith(".jsonl"):
                out.append({"file": f"{hook}/{name}", "size": os.path.getsize(os.path.join(folder, name))})
    return out


def resolve(file: str) -> str | None:
    """Path of `<hook>/<name>.jsonl` under DATA, or None for anything else (no dots, so no `..`)."""
    hook, _, name = file.partition("/")
    if not (NAME.fullmatch(hook) and name.endswith(".jsonl") and NAME.fullmatch(name[:-6])):
        return None
    path = os.path.join(DATA, hook, name)
    return path if os.path.isfile(path) else None


def tail(path: str, rows: int) -> list[dict]:
    with open(path, "rb") as f:
        size = f.seek(0, 2)
        start = max(0, size - CHUNK)
        f.seek(start)
        lines = f.read().split(b"\n")
    if start:
        lines = lines[1:]  # starts mid-line
    records = []
    for line in lines[-rows - 1:]:
        try:
            records.append(json.loads(line))
        except ValueError:
            pass  # a line another hook is still writing
    return records[-rows:]


def add_status(records: list[dict], file: str):
    """Mark each `use` decision followed / pending / ignored? from the followed log, when it exists."""
    if not file.endswith("decisions.jsonl") or not os.path.exists(followed_log.path):
        return
    router = "SKILL" if file.startswith("skill_router") else "MODEL"
    used = [{**r, "router": router} for r in records if r.get("decision") == "use" and r.get("session_id")]
    pending, followed = list(used), set()
    for action in sorted(tail(followed_log.path, MAX_ROWS), key=lambda a: a["timestamp"]):
        match = matching_decision(action, pending)
        if match is not None:
            pending.remove(match)
            followed.add(match["timestamp"])
    now = time.time()
    for r in records:
        if r.get("decision") == "use" and r.get("session_id"):
            r["status"] = ("followed" if r["timestamp"] in followed
                           else "pending" if now - r["timestamp"] < IGNORE_AFTER_SECONDS else "ignored?")


def read_log(file: str, rows: int, prompts: bool) -> list[dict] | None:
    path = resolve(file)
    if path is None:
        return None
    records = tail(path, rows)
    add_status(records, file)
    if not prompts:
        for r in records:
            if "input_text" in r:
                r["input_text"] = "(hidden)"
    return records


def list_commands() -> list[dict]:
    return [{"name": n, "usage": u, "purpose": p} for n, (_, u, p) in COMMANDS.items() if n not in NOT_HERE]


def run_command(name: str, args: str) -> dict | None:
    """Run a CLI command and return its output; None for a name that is not offered here."""
    if name not in COMMANDS or name in NOT_HERE:
        return None
    try:
        # posix=False keeps Windows backslashes, but also the quote marks: drop one matching pair per word.
        words = [w[1:-1] if len(w) > 1 and w[0] == w[-1] and w[0] in "\"'" else w for w in shlex.split(args, posix=False)]
        argv = resolve_command([name, *words])
        done = subprocess.run([sys.executable, *argv], cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=RUN_TIMEOUT)
    except ValueError as e:
        return {"code": 2, "output": f"bad arguments: {e}"}
    except subprocess.TimeoutExpired:
        return {"code": 124, "output": f"timed out after {RUN_TIMEOUT}s"}
    return {"code": done.returncode, "output": done.stdout + done.stderr}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status: int, body: bytes, kind: str):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value):
        self._send(status, json.dumps(value).encode(), "application/json")

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "").rsplit(":", 1)[0] in HOSTS

    def do_POST(self):
        # A JSON content type forces a CORS preflight this server never grants, so other sites cannot run commands.
        if not self._host_ok() or self.headers.get("Content-Type") != "application/json":
            return self._json(403, {"error": "forbidden"})
        if urlparse(self.path).path != "/api/run":
            return self._json(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096)))
            result = run_command(str(body["name"]), str(body.get("args", "")))
        except (ValueError, KeyError, TypeError, AttributeError):
            return self._json(400, {"error": "need {name, args}"})
        if result is None:
            return self._json(404, {"error": "no such command"})
        self._json(200, result)

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "forbidden host"})
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/":
            with open(PAGE, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if url.path == "/api/commands":
            return self._json(200, list_commands())
        if url.path == "/api/logs":
            return self._json(200, list_logs())
        if url.path == "/api/tail":
            try:
                rows = max(1, min(int(query.get("rows", ["200"])[0]), MAX_ROWS))
            except ValueError:
                return self._json(400, {"error": "rows must be a number"})
            records = read_log(query.get("file", [""])[0], rows, query.get("prompts") == ["1"])
            if records is None:
                return self._json(404, {"error": "no such log"})
            return self._json(200, records)
        self._json(404, {"error": "not found"})


def main(argv: list[str]) -> int:
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8765
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print(f"Cannot listen on port {port}: {e}", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"Hook logs at {url}  (Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
