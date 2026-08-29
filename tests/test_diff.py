import tempfile
from pathlib import Path

import loom
from loom.cache import DiskCache
from loom.diff import diff_runs, first_divergence


def test_diff_identical_runs_have_no_divergence():
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=Path(tmp) / "cache")

        @loom.step(cache=cache)
        def f(x):
            return x + 1

        with loom.Run("a", cache=cache, root=Path(tmp) / "runs") as run1:
            f(1)
        with loom.Run("b", cache=cache, root=Path(tmp) / "runs") as run2:
            f(1)

        assert first_divergence(run1, run2) is None


def test_diff_flags_first_changed_node():
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=Path(tmp) / "cache")

        @loom.step(cache=cache)
        def f(x):
            return x + 1

        @loom.step(cache=cache)
        def g(y):
            return y * 2

        def pipeline(x):
            return g(f(x))

        with loom.Run("a", cache=cache, root=Path(tmp) / "runs") as run1:
            pipeline(1)
        with loom.Run("b", cache=cache, root=Path(tmp) / "runs") as run2:
            pipeline(2)

        d = first_divergence(run1, run2)
        assert d is not None
        assert d.index == 0
        assert d.step_name.endswith("f")


def test_diff_runs_reports_all_nodes_in_order():
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=Path(tmp) / "cache")

        @loom.step(cache=cache)
        def f(x):
            return x + 1

        with loom.Run("a", cache=cache, root=Path(tmp) / "runs") as run1:
            f(1)
        with loom.Run("b", cache=cache, root=Path(tmp) / "runs") as run2:
            f(1)
            f(2)  # run2 has one extra node

        diffs = diff_runs(run1, run2)
        assert len(diffs) == 2
        assert diffs[0].status == "same"
        assert diffs[1].status == "only_in_b"
