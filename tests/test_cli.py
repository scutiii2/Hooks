"""The CLI's short names resolve to the same commands the README used to spell out."""
import importlib.util
import os

import pytest

from core.py.tools import cli


def test_short_names_and_module_paths():
    assert cli.resolve(["skill_router", "status"]) == ["-m", "hooks.skill_router.toggle", "status"]
    assert cli.resolve(["web", "--port", "9"]) == ["-m", "core.py.tools.web", "--port", "9"]
    assert cli.resolve(["hooks.skill_router.pick", "x y"]) == ["-m", "hooks.skill_router.pick", "x y"]
    assert cli.resolve([]) is None
    with pytest.raises(SystemExit, match="Unknown name 'skil_router'"):
        cli.resolve(["skil_router", "status"])


@pytest.mark.parametrize("name", list(cli.COMMANDS))
def test_every_name_points_at_something_that_exists(name):
    args = cli.COMMANDS[name][0]
    if args[0] == "-m":
        assert importlib.util.find_spec(args[1]) is not None, args[1]
    else:
        assert os.path.isfile(os.path.join(cli.ROOT, args[0])), args[0]


def test_menu_quits_on_blank_and_runs_choice(monkeypatch):
    answers = iter([""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert cli.menu() is None
    answers = iter(["1", "status"])
    assert cli.menu() == ["-m", "hooks.skill_router.toggle", "status"]
