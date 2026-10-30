from core.py.hook_io import should_skip
from core.py.privacy import is_private


def test_short_real_prompts_are_routed():
    assert not should_skip("Write a poem")
    assert not should_skip("Fix the bug")


def test_context_replies_are_skipped():
    assert should_skip("yes")
    assert should_skip("ok do it")
    assert should_skip("")


def test_identifier_is_not_a_key():
    assert not is_private("rename CamelCaseIdentifierHere12 please")


def test_key_shaped_blob_is_private():
    assert is_private("use aB3dE9fG7hJ2kL5mN8pQ1rS4tU6vW0xY")


def test_concurrent_increments_are_not_lost(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from core.py.json_store import JsonStore

    class Counter(JsonStore):
        path = str(tmp_path / "c.json")
        defaults = {"n": 0}

    c = Counter()
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: c.increment("n"), range(100)))
    assert c.read()["n"] == 100
