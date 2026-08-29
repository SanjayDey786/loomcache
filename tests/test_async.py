import asyncio
import tempfile
from pathlib import Path

import pytest

import loom
from loom.async_run import AsyncRun, async_step, gather
from loom.cache import DiskCache


@pytest.mark.asyncio
async def test_async_step_caching():
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=Path(tmp) / "cache")
        call_count = 0

        @async_step(cache=cache)
        async def async_add(x: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # simulate I/O
            return x + 1

        # First run
        async with AsyncRun("test", cache=cache, root=Path(tmp) / "runs") as run1:
            result = await async_add(5)
        assert result == 6
        assert call_count == 1
        assert run1.nodes[0].cache_hit is False

        # Second run – cache hit
        async with AsyncRun("test2", cache=cache, root=Path(tmp) / "runs") as run2:
            result2 = await async_add(5)
        assert result2 == 6
        assert call_count == 1  # no extra execution
        assert run2.nodes[0].cache_hit is True


@pytest.mark.asyncio
async def test_gather():
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=Path(tmp) / "cache")
        calls = {"a": 0, "b": 0}

        @async_step(cache=cache)
        async def a(x: int) -> int:
            calls["a"] += 1
            await asyncio.sleep(0.01)
            return x * 2

        @async_step(cache=cache)
        async def b(y: int) -> int:
            calls["b"] += 1
            await asyncio.sleep(0.01)
            return y + 10

        async with AsyncRun("gather_test", cache=cache, root=Path(tmp) / "runs") as run:
            results = await gather(a(1), b(2))
            # Results are unordered, but we can check
            assert set(results) == {2, 12}
        # Both steps executed once
        assert calls["a"] == 1
        assert calls["b"] == 1
        assert len(run.nodes) == 2

        # Re-run – cache hits
        async with AsyncRun("gather_test2", cache=cache, root=Path(tmp) / "runs") as run2:
            results2 = await gather(a(1), b(2))
        assert results2 == results
        assert calls["a"] == 1
        assert calls["b"] == 1
        assert all(n.cache_hit for n in run2.nodes)