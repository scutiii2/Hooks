"""Resident Laya classifier. Loading Laya takes ~35 s, far over a hook's timeout, so one background
process loads it once and the hooks ask it over loopback HTTP (127.0.0.1 only, nothing leaves the machine).

    python -m router.core.laya_server [serve|status|stop]

A hook that finds no server fails fast (the router then behaves as if absent) and starts one in the
background; prompts after it has loaded (~35 s) are classified.
"""
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .classifiers import Classifier, ClassifierError, LayaClassifier

HOST = "127.0.0.1"
LOG_PATH = os.path.join(config.ROOT, "laya_server.log")
MAX_BODY = 1_000_000
_BREAKAWAY = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except ConnectionError:  # the client gave up (a hook timed out) before the answer was written
            pass

    def _reply(self, status: int, body: dict):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply(200, {"ok": True}) if self.path == "/health" else self._reply(404, {"error": "not found"})

    def do_POST(self):
        # A browser page cannot send application/json cross-origin without a preflight, so this keeps web pages out.
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._reply(415, {"error": "application/json required"})
        if self.path == "/shutdown":
            self._reply(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path != "/ask":
            return self._reply(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError("bad body size")
            data = json.loads(self.rfile.read(length))
            subject, criteria = data["subject"], data["criteria"]
            if not isinstance(subject, str) or not isinstance(criteria, dict) or len(criteria) < 2:
                raise ValueError("subject must be a string, criteria an object of 2+ options")
        except (ValueError, KeyError, TypeError) as error:
            return self._reply(400, {"error": f"bad request: {error}"})
        try:
            with self.server.lock:  # one model, one prediction at a time
                result = self.server.classifier.ask_choice(subject, criteria, timeout=0)
        except ClassifierError as error:
            return self._reply(500, {"error": str(error)})
        self._reply(200, result)


class _ExclusiveServer(ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows SO_REUSEADDR lets a second process bind the same port


def serve(port: int):
    # Bind before loading the model: a second copy fails here at once instead of loading 1.6 GB.
    try:
        server = _ExclusiveServer((HOST, port), _Handler)
    except OSError as error:
        print(f"laya server not started, {HOST}:{port} unavailable: {error}", file=sys.stderr)
        sys.exit(1)
    server.classifier = LayaClassifier()
    server.lock = threading.Lock()
    server.classifier._get_router()
    print(f"laya server ready on {HOST}:{port}", flush=True)
    server.serve_forever()


def _spawn():
    """Start a detached server; output goes to laya_server.log."""
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    # Claude Code may run hooks inside a job object that kills its children; breakaway lets the server outlive it.
    attempts = [flags | _BREAKAWAY, flags] if os.name == "nt" else [flags]
    # pythonw has no console, so there is no window to close by accident (closing it would kill the server).
    python = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(python):
        python = sys.executable
    with open(LOG_PATH, "ab") as log:
        for attempt in attempts:
            try:
                subprocess.Popen(
                    [python, "-m", "router.core.laya_server", "serve"], cwd=config.ROOT,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=attempt,
                    start_new_session=os.name != "nt", close_fds=True,
                )
                return
            except OSError:  # the job does not allow breakaway: start without it
                if attempt == attempts[-1]:
                    raise


class RemoteLayaClassifier(Classifier):
    """Same answers as LayaClassifier, from the resident server."""

    def __init__(self, port: int | None = None):
        self.port = port or config.get_laya_server_port()

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        request = urllib.request.Request(
            f"http://{HOST}:{self.port}{path}", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise ClassifierError(f"laya server: {error.read().decode('utf-8', errors='replace')}") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, ConnectionRefusedError):
                _spawn()
                raise ClassifierError("laya server was not running; starting it (~35 s to load)") from error
            raise ClassifierError(f"laya server unreachable: {error.reason}") from error
        except (TimeoutError, OSError, ValueError) as error:
            raise ClassifierError(f"laya server did not answer in time (still loading?): {error}") from error

    def ask_choice(self, subject: str, criteria: dict, timeout: float) -> dict:
        body = self._post("/ask", {"subject": subject, "criteria": criteria}, timeout)
        try:
            return {"choice": body["choice"], "confidence": int(body["confidence"])}
        except (KeyError, TypeError, ValueError) as error:
            raise ClassifierError(f"laya server sent an unexpected answer: {body!r}") from error


def main(argv: list[str]) -> int:
    action = argv[0] if argv else "serve"
    port = config.get_laya_server_port()
    if action == "serve":
        serve(port)
        return 0
    client = RemoteLayaClassifier(port)
    try:
        if action == "start":
            try:
                urllib.request.urlopen(f"http://{HOST}:{port}/health", timeout=2).close()
                print(f"already running on {HOST}:{port}")
            except OSError:
                _spawn()
                print("starting in the background (~35 s to load); output in laya_server.log")
        elif action == "status":
            with urllib.request.urlopen(f"http://{HOST}:{port}/health", timeout=2):
                print(f"running on {HOST}:{port}")
        elif action == "stop":
            client._post("/shutdown", {}, 2)
            print("stopped")
        else:
            print("Usage: python -m router.core.laya_server [serve|start|status|stop]")
            return 1
    except (urllib.error.URLError, OSError, ClassifierError):
        print("not running")
        return 0 if action == "stop" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
