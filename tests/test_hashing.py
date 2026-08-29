from loom import hashing


def test_hash_value_stable_regardless_of_dict_key_order():
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert hashing.hash_value(a) == hashing.hash_value(b)


def test_hash_value_differs_for_different_values():
    assert hashing.hash_value("a") != hashing.hash_value("b")


def test_hash_value_uses_upstream_node_hash_when_traced():
    class FakeNode:
        node_hash = "abc123"

    class Traced:
        _loom_node = FakeNode()

    assert hashing.hash_value(Traced()) == "node:abc123"


def test_hash_source_changes_when_function_body_changes():
    def f_v1(x):
        return x + 1

    def f_v2(x):
        return x + 2

    assert hashing.hash_source(f_v1) != hashing.hash_source(f_v2)


def test_hash_source_stable_for_unchanged_function():
    def f(x):
        return x + 1

    assert hashing.hash_source(f) == hashing.hash_source(f)


def test_hash_node_deterministic():
    h1 = hashing.hash_node("step", "srchash", (1, 2), {"a": 3})
    h2 = hashing.hash_node("step", "srchash", (1, 2), {"a": 3})
    assert h1 == h2


def test_hash_node_changes_with_different_args():
    h1 = hashing.hash_node("step", "srchash", (1,), {})
    h2 = hashing.hash_node("step", "srchash", (2,), {})
    assert h1 != h2


def test_hash_node_changes_with_different_source():
    h1 = hashing.hash_node("step", "srchash_a", (1,), {})
    h2 = hashing.hash_node("step", "srchash_b", (1,), {})
    assert h1 != h2
