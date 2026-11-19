"""A .bat file with LF endings breaks on Windows (labels and `call` misbehave): the checkout must keep CRLF."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_bat_files_are_crlf():
    bats = [p for p in ROOT.rglob("*.bat") if ".venv" not in p.parts and ".git" not in p.parts]
    assert bats
    for p in bats:
        data = p.read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n"), f"{p.name} has bare LF line endings"


def test_gitattributes_pins_bat_to_crlf():
    assert "*.bat text eol=crlf" in (ROOT / ".gitattributes").read_text()
