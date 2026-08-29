import tempfile
from pathlib import Path

import loom
from loom.cache import DiskCache


def _cache(tmp):
    return DiskCache(root=Path(tmp) / "cache")


def test_step_executes_once_and_caches_on_repeat_calls():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        calls = {"count": 0}

        @loom.step(cache=cache)
        def add_one(x: int) -> int:
            calls["count"] += 1
            return x + 1

        with loom.Run("t", cache=cache, root=Path(tmp) / "runs") as run1:
            r1 = add_one(1)
        with loom.Run("t", cache=cache, root=Path(tmp) / "runs") as run2:
            r2 = add_one(1)

        assert r1 == 2
        assert r2 == 2
        assert calls["count"] == 1  # second call was a cache hit
        assert run1.nodes[0].cache_hit is False
        assert run2.nodes[0].cache_hit is True


def test_downstream_step_reruns_when_upstream_input_changes():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        counts = {"a": 0, "b": 0}

        @loom.step(cache=cache)
        def step_a(x: int) -> int:
            counts["a"] += 1
            return x * 2

        @loom.step(cache=cache)
        def step_b(y: int) -> int:
            counts["b"] += 1
            return y + 100

        def pipeline(x):
            return step_b(step_a(x))

        with loom.Run("p", cache=cache, root=Path(tmp) / "runs"):
            pipeline(1)
        with loom.Run("p", cache=cache, root=Path(tmp) / "runs"):
            pipeline(2)  # different input -> both steps must re-execute

        assert counts["a"] == 2
        assert counts["b"] == 2

        with loom.Run("p", cache=cache, root=Path(tmp) / "runs") as run3:
            pipeline(1)  # same as the very first call -> fully cached

        assert counts["a"] == 2
        assert counts["b"] == 2
        assert all(n.cache_hit for n in run3.nodes)


def test_only_downstream_step_reruns_when_only_it_changes():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        counts = {"a": 0, "b": 0}

        @loom.step(cache=cache)
        def step_a(x: int) -> int:
            counts["a"] += 1
            return x * 2

        @loom.step(cache=cache)
        def step_b(y: int, salt: int) -> int:
            counts["b"] += 1
            return y + salt

        with loom.Run("p", cache=cache, root=Path(tmp) / "runs"):
            a = step_a(1)
            step_b(a, salt=1)

        with loom.Run("p", cache=cache, root=Path(tmp) / "runs"):
            a = step_a(1)  # identical -> cache hit, does NOT re-execute
            step_b(a, salt=2)  # different salt -> re-executes

        assert counts["a"] == 1  # step_a only ran once across both runs
        assert counts["b"] == 2  # step_b ran for each distinct salt


def test_fork_reuses_cache_for_unaffected_steps():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        counts = {"a": 0, "b": 0}

        @loom.step(cache=cache)
        def step_a(x: int) -> int:
            counts["a"] += 1
            return x * 2

        @loom.step(cache=cache)
        def step_b(y: int) -> int:
            counts["b"] += 1
            return y + 1

        def pipeline(x):
            return step_b(step_a(x))

        with loom.Run("p", cache=cache, root=Path(tmp) / "runs") as run1:
            pipeline(5)

        run2 = run1.fork(pipeline, x=5)  # identical input -> fully cached fork
        assert counts["a"] == 1
        assert counts["b"] == 1
        assert all(n.cache_hit for n in run2.nodes)


def test_run_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)

        @loom.step(cache=cache)
        def f(x: int) -> int:
            return x + 1

        with loom.Run("roundtrip", cache=cache, root=Path(tmp) / "runs") as run:
            f(1)
        path = run.save()

        loaded = loom.Run.load(path)
        assert loaded.name == "roundtrip"
        assert len(loaded.nodes) == 1
        assert loaded.nodes[0].step_name.endswith("f")
        assert loaded.nodes[0].cache_hit is False


def test_run_stats_report_hit_rate():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)

        @loom.step(cache=cache)
        def f(x: int) -> int:
            return x + 1

        with loom.Run("s", cache=cache, root=Path(tmp) / "runs"):
            f(1)
        with loom.Run("s", cache=cache, root=Path(tmp) / "runs") as run2:
            f(1)

        stats = run2.stats()
        assert stats["total_nodes"] == 1
        assert stats["cache_hits"] == 1
        assert stats["hit_rate"] == 1.0
