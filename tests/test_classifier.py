"""Offline assert-based tests; also runnable without pytest."""
import io
import json
import os
import urllib.error
from unittest.mock import patch

CRITERIA = {"tiny": "a", "large": "b"}


def _call(body=None, error=None, key="k"):
    from src.core.classifiers import JevClassifier

    response = io.BytesIO(json.dumps(body).encode()) if body is not None else None
    opener = patch("urllib.request.urlopen", side_effect=error) if error else \
        patch("urllib.request.urlopen", return_value=response)
    with patch.dict(os.environ, {"TYPESAFE_API_KEY": key}), opener:
        return JevClassifier().ask_choice("msg", CRITERIA, 1.0)


def _fails(**kwargs) -> bool:
    from src.core.classifiers import ClassifierError

    try:
        _call(**kwargs)
    except ClassifierError:
        return True
    return False


def _answer(choice="tiny", confidence=0.8):
    return {"answers": {"answer": {"choice": choice, "confidence": confidence}}}


def test_jev_scales_confidence_to_percent():
    assert _call(_answer("large", 0.724)) == {"choice": "large", "confidence": 72}


def test_jev_rejects_bad_responses():
    assert _fails(body=_answer("huge"))  # option that was not offered
    assert _fails(body=_answer(confidence=1.5))
    assert _fails(body=_answer(confidence=True))
    assert _fails(body={"answers": {}})
    assert _fails(body=_answer(), key="")  # no API key


def test_jev_wraps_network_errors():
    assert _fails(error=urllib.error.URLError("down"))
    assert _fails(error=TimeoutError())
    assert _fails(error=urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"x")))


def test_classify_size_rejects_unknown_size():
    from src.core.classifiers import Classifier, ClassifierError

    class Fake(Classifier):
        def ask_choice(self, subject, criteria, timeout):
            return {"choice": "huge", "confidence": 90}

    try:
        Fake().classify_size("x")
    except ClassifierError:
        return
    raise AssertionError("unknown size accepted")


def test_config_precedence():
    from src.core import config

    with patch.dict(os.environ, {"CONFIDENCE_THRESHOLD": "42"}):
        assert config.get_confidence_threshold() == 42
    with patch.dict(os.environ, {"CONFIDENCE_THRESHOLD": ""}), \
            patch.object(config, "_read_config", return_value={"confidence_threshold": {"jev": 71}}):
        assert config.get_confidence_threshold() == 71
    with patch.dict(os.environ, {"CONFIDENCE_THRESHOLD": ""}), patch.object(config, "CONFIG_PATH", "missing.json"):
        assert config.get_confidence_threshold() == 60


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print(f"PASS {name}")
