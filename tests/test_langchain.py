import pytest

try:
    from langchain_core.runnables import Runnable, RunnableConfig
except ImportError:
    Runnable = None
    RunnableConfig = None

from loom.langchain import wrap_runnable
from loom import Run, step
from loom.cache import DiskCache
import tempfile
from pathlib import Path


@pytest.mark.skipif(Runnable is None, reason="langchain-core not installed")
def test_langchain_wrapper():
    # Create a dummy Runnable that counts calls
    class DummyRunnable(Runnable):
        def __init__(self):
            self.call_count = 0

        def invoke(self, input, config=None, **kwargs):
            self.call_count += 1
            return {"result": input["x"] + 1}

    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=Path(tmp) / "cache")
        runnable = DummyRunnable()
        wrapped = wrap_runnable(runnable, name="dummy", cache=cache)

        # First run – should execute
        with Run("test", cache=cache, root=Path(tmp) / "runs") as r:
            out1 = wrapped.invoke({"x": 10})
        assert out1 == {"result": 11}
        assert runnable.call_count == 1

        # Second run – should be cached
        with Run("test2", cache=cache, root=Path(tmp) / "runs") as r2:
            out2 = wrapped.invoke({"x": 10})
        assert out2 == {"result": 11}
        assert runnable.call_count == 1  # no extra invoke

        # Different input – should re-execute
        with Run("test3", cache=cache, root=Path(tmp) / "runs") as r3:
            out3 = wrapped.invoke({"x": 20})
        assert out3 == {"result": 21}
        assert runnable.call_count == 2

        # Verify nodes are recorded
        assert len(r.nodes) == 1
        assert r.nodes[0].cache_hit is False
        assert len(r2.nodes) == 1
        assert r2.nodes[0].cache_hit is True