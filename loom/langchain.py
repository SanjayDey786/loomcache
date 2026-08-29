"""LangChain adapter: cache any Runnable via Loom.

    from loom.langchain import wrap_runnable
    from langchain.chains import LLMChain

    chain = LLMChain(...)
    cached_chain = wrap_runnable(chain, name="my_chain")

    with loom.Run("run") as run:
        result = cached_chain.invoke({"input": "Hello"})
"""

from __future__ import annotations

import hashlib
import inspect
import time
from typing import Any, Optional, TypeVar

from loom import current_run, default_cache, attach_node, hashing
from loom.run import Node
from loom.cache import Cache

try:
    from langchain_core.runnables import Runnable, RunnableConfig
except ImportError:
    # Stub for optional dependency
    class Runnable:  # type: ignore[no-redef]
        pass

    RunnableConfig = Any

T = TypeVar("T", bound=Runnable)


class CachedRunnable(Runnable):
    """A Runnable that delegates to the original and caches invoke results."""

    def __init__(
        self,
        runnable: Runnable,
        *,
        name: Optional[str] = None,
        cache: Optional[Cache] = None,
        version: Optional[str] = "",
        source_hash: Optional[str] = None,
    ):
        self._runnable = runnable
        self._cache = cache or default_cache()
        self._name = name or getattr(runnable, "name", None) or runnable.__class__.__name__
        self._version = version or ""

        if source_hash is None:
            try:
                src = inspect.getsource(runnable.invoke)
                source_hash = hashlib.sha256(src.encode()).hexdigest()
            except (OSError, TypeError):
                source_hash = "unknown"
        self._source_hash = source_hash

    def _cache_key(self, input: Any, config: Optional[RunnableConfig] = None) -> str:
        identity = f"langchain:{self._name}:{self._source_hash}:{self._version}"
        input_hash = hashing.hash_value(input)
        return hashing.hash_node(
            step_name=self._name,
            source_hash=identity,
            args=(input_hash,),
            kwargs={},
            extra="langchain",
        )

    def invoke(self, input: Any, config: Optional[RunnableConfig] = None, **kwargs) -> Any:
        run = current_run()
        if run is None:
            return self._runnable.invoke(input, config, **kwargs)

        key = self._cache_key(input, config)
        entry = self._cache.get(key)

        if entry is not None:
            output = entry.output
            cache_hit = True
            duration = 0.0
            time_saved = entry.metadata.get("duration_s", 0.0)
        else:
            start = time.time()
            output = self._runnable.invoke(input, config, **kwargs)
            duration = time.time() - start
            self._cache.put(
                key,
                output,
                metadata={
                    "step_name": self._name,
                    "timestamp": time.time(),
                    "duration_s": duration,
                },
            )
            cache_hit = False
            time_saved = 0.0

        node = Node(
            node_hash=key,
            step_name=self._name,
            parents=[],
            cache_hit=cache_hit,
            duration_s=duration,
            time_saved_s=time_saved,
            timestamp=time.time(),
            args_repr=repr(input),
            kwargs_repr=repr(config),
            output_repr=repr(output),
        )
        run.record(node)
        return attach_node(output, node)

    # Async and batch methods are not yet implemented (v1.0 roadmap).
    async def ainvoke(self, input: Any, config: Optional[RunnableConfig] = None, **kwargs) -> Any:
        raise NotImplementedError("Async caching is not yet supported for Runnables.")

    def batch(self, inputs, config=None, **kwargs):
        raise NotImplementedError("Batch caching is not yet supported.")


def wrap_runnable(
    runnable: T,
    *,
    name: Optional[str] = None,
    cache: Optional[Cache] = None,
    version: Optional[str] = "",
    source_hash: Optional[str] = None,
) -> T:
    """Wrap a LangChain Runnable with Loom caching."""
    return CachedRunnable(runnable, name=name, cache=cache, version=version, source_hash=source_hash)