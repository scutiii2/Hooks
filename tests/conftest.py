import os

import pytest

from core.py import runlog


@pytest.fixture(autouse=True)
def runs_dir(tmp_path, monkeypatch):
    """Keep run logs written by hooks under test out of the real .data/ folder."""
    monkeypatch.setattr(runlog, "data_path", lambda hook, name: os.path.join(tmp_path, hook, name))
    return tmp_path
