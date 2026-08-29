"""Async execution support for Loom.

Use `AsyncRun` in an async context manager with async steps.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, Union

from loom import hashing, default_cache
from loom.run import Node, current_run
from loom.tracing import attach_node, get_node, unwrap_recursive
from loom.cache import Cache

_current_async_run: contextvars.ContextVar = contextvars.ContextVar(
    "loom_current_async_run", default=None
)


class AsyncRun:
    """Async context manager for recording async step executions."""

    def __init__(
        self,
        name: str,
        cache: Optional[Cache] = None,
        root: Union[str, Path] = ".loom_runs",
    ):
        self.name = name
        self.run_id = f"{name}-{uuid.uuid4().hex[:8]}"
        self.cache = cache or default_cache()
        self.root = Path(root)
        self.nodes: list = []
        self.created_at = time.time()
        self._token = None

    async def __aenter__(self) -> AsyncRun:
        self._token = _current_async_run.set(self)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        _current_async_run.reset(self._token)

    def record(self, node: Node) -> None:
        self.nodes.append(node)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "created_at": self.created_at,
            "nodes": [n.to_dict() for n in self.nodes],
        }

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        out_path = Path(path) if path else self.root / f"{self.run_id}.json"
        out_path.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return out_path

    def stats(self) -> dict:
        hits = sum(1 for n in self.nodes if n.cache_hit)
        total = len(self.nodes)
        return {
            "total_nodes": total,
            "cache_hits": hits,
            "cache_misses": total - hits,
            "hit_rate": (hits / total) if total else 0.0,
            "wall_time_s": round(sum(n.duration_s for n in self.nodes), 3),
            "time_saved_s": round(sum(n.time_saved_s for n in self.nodes), 3),
        }

    @classmethod
    def load(cls, path: Union[str, Path]) -> AsyncRun:
        data = json.loads(Path(path).read_text())
        run = cls.__new__(cls)
        run.name = data["name"]
        run.run_id = data["run_id"]
        run.created_at = data["created_at"]
        run.cache = default_cache()
        run.root = Path(path).parent
        run.nodes = [Node(**n) for n in data["nodes"]]
        run._token = None
        return run


def async_step(func: Optional[Callable] = None, *, cache: Optional[Cache] = None):
    """Decorator that works for async functions.

    If the function is async, it returns a coroutine that will be awaited
    by the caller. For sync functions, use `@loom.step` instead.
    """

    def decorator(f: Callable) -> Callable:
        source_hash = hashing.hash_source(f)
        is_coroutine = asyncio.iscoroutinefunction(f)

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs):
            run = _current_async_run.get()
            if run is None:
                # Fallback to calling the function directly (could be sync or async)
                if is_coroutine:
                    return await f(*args, **kwargs)
                else:
                    return f(*args, **kwargs)

            active_cache = cache or (run.cache if run is not None else default_cache())
            node_hash = hashing.hash_node(f.__qualname__, source_hash, args, kwargs)

            # Determine parents from traced arguments
            parents = [
                n.node_hash
                for n in (get_node(a) for a in list(args) + list(kwargs.values()))
                if n is not None
            ]

            entry = active_cache.get(node_hash)
            if entry is not None:
                output = entry.output          # already clean
                cache_hit = True
                duration = 0.0
                time_saved = float(entry.metadata.get("duration_s", 0.0))
                clean_output = output
            else:
                # Unwrap arguments
                from loom.run import _unwrap
                call_args = tuple(_unwrap(a) for a in args)
                call_kwargs = {k: _unwrap(v) for k, v in kwargs.items()}
                t0 = time.time()
                if is_coroutine:
                    raw_output = await f(*call_args, **call_kwargs)
                else:
                    raw_output = f(*call_args, **call_kwargs)
                duration = time.time() - t0

                clean_output = unwrap_recursive(raw_output)

                active_cache.put(
                    node_hash,
                    clean_output,
                    metadata={
                        "step_name": f.__qualname__,
                        "timestamp": time.time(),
                        "duration_s": duration,
                    },
                )
                cache_hit = False
                time_saved = 0.0

            node = Node(
                node_hash=node_hash,
                step_name=f.__qualname__,
                parents=parents,
                cache_hit=cache_hit,
                duration_s=duration,
                time_saved_s=time_saved,
                timestamp=time.time(),
                args_repr=repr(args),
                kwargs_repr=repr(kwargs),
                output_repr=repr(clean_output),
            )
            run.record(node)
            return attach_node(clean_output, node)

        return async_wrapper

    if func is not None:
        return decorator(func)
    return decorator


async def gather(*coros, return_exceptions=False):
    """Run multiple async steps concurrently, with Loom tracking."""
    return await asyncio.gather(*coros, return_exceptions=return_exceptions)