"""Offline assert-based tests; also runnable without pytest."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from router.core.classifiers import (
    Classifier, ClassifierError, FallbackClassifier, LayaModelClassifier, SIZE_CRITERIA,
)


class _Stub(BaseHTTPRequestHandler):
    seen = {}

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Stub.seen = {"path": self.path, "body": body, "token": self.headers.get("X-Internal-Token")}
        reply = {"answers": {"choice": {"type": "choice", "choice": "large", "answer_confidence": 0.42}}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _Fixed(Classifier):
    def __init__(self, result=None):
        self.result, self.calls = result, 0

    def ask_choice(self, subject, criteria, timeout):
        self.calls += 1
        if self.result is None:
            raise ClassifierError("down")
        return dict(self.result)


def test_laya_model_request_and_answer(monkeypatch=None):
    import os
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["LAYA_TOKEN"] = "t0k"
    try:
        result = LayaModelClassifier(f"http://127.0.0.1:{server.server_port}", "english-only").classify_size("hi", 2)
    finally:
        server.shutdown()
        del os.environ["LAYA_TOKEN"]
    assert result == {"size": "large", "confidence": 42, "provider": "laya"}
    assert _Stub.seen["path"] == "/v1/ask" and _Stub.seen["token"] == "t0k"
    assert _Stub.seen["body"]["strategy"] == "english-only" and _Stub.seen["body"]["text"] == "hi"
    assert _Stub.seen["body"]["questions"]["choice"]["criteria"] == SIZE_CRITERIA


def test_unreachable_laya_raises_classifier_error():
    try:
        LayaModelClassifier("http://127.0.0.1:1", "auto").ask_choice("hi", SIZE_CRITERIA, 1)
    except ClassifierError:
        return
    raise AssertionError("expected ClassifierError")


def test_fallback_uses_jev_and_tags_provider():
    laya, jev = _Fixed(), _Fixed({"choice": "tiny", "confidence": 90})
    chain = FallbackClassifier(laya, "laya", jev, "jev")
    assert chain.classify_size("hi", 3) == {"size": "tiny", "confidence": 90, "provider": "jev"}
    chain.classify_size("hi again", 3)
    assert laya.calls == 1 and jev.calls == 2  # Laya is tried once per process


def test_fallback_prefers_laya():
    laya, jev = _Fixed({"choice": "large", "confidence": 50}), _Fixed({"choice": "tiny", "confidence": 90})
    result = FallbackClassifier(laya, "laya", jev, "jev").classify_size("hi", 3)
    assert result["provider"] == "laya" and jev.calls == 0


def test_both_down_raises():
    try:
        FallbackClassifier(_Fixed(), "laya", _Fixed(), "jev").classify_size("hi", 3)
    except ClassifierError:
        return
    raise AssertionError("expected ClassifierError")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
