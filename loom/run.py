"""Core execution-tracking primitives: steps, nodes, and runs.

    @loom.step
    def plan(query: str) -> str:
        return llm_call(f"Plan: {query}")

    with loom.Run("my-pipeline") as run:
        result = plan("hello world")
    run.save()

Every `@loom.step` call made while a `Run` is active is hashed,
looked up in the cache, executed only on a miss, and recorded onto
`run.nodes` in order.
"""
from __future__ import annotations

import contextvars
import functools
import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Optional, Union

from . import hashing
from .cache import Cache, default_cache
from .tracing import attach_node, get_node, TracedBox, unwrap_recursive

_current_run: contextvars.ContextVar = contextvars.ContextVar(
    "loom_current_run", default=None
)


def current_run() -> Optional["Run"]:
    """The `Run` currently active via a `with loom.Run(...)` block, if any."""
    return _current_run.get()


@dataclass
class Node:
    """One recorded execution (or cache hit) of a single `@step` call."""

    node_hash: str
    step_name: str
    parents: list
    cache_hit: bool
    duration_s: float
    time_saved_s: float
    timestamp: float
    args_repr: str
    kwargs_repr: str
    output_repr: str

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_repr(value: Any, limit: int = 300) -> str:
    try:
        text = repr(value)
    except Exception:
        text = f"<unrepr-able {type(value).__name__}>"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _unwrap(value: Any) -> Any:
    if isinstance(value, TracedBox):
        return value.unwrap()
    return value


class Run:
    """A single execution of a pipeline.

    Use as a context manager. Every `@step` call made while this Run is
    active gets recorded, in order, into `run.nodes`.
    """

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

    # -- context manager ------------------------------------------------
    def __enter__(self) -> "Run":
        self._token = _current_run.set(self)
        return self

    def __exit__(self, exc_type, exc, tb):
        _current_run.reset(self._token)
        return False

    # -- recording --------------------------------------------------------
    def record(self, node: Node) -> None:
        self.nodes.append(node)

    # -- persistence --------------------------------------------------------
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

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Run":
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

    # -- introspection --------------------------------------------------------
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

    def fork(self, pipeline_fn: Callable, name: Optional[str] = None, **new_kwargs) -> "Run":
        """Re-run `pipeline_fn` (typically with one input changed).

        Because every `@step` call is content-addressed, any step whose
        hash is unaffected by the change is served from cache instantly;
        only the changed step and everything downstream of it actually
        re-executes. This mirrors how `bazel build` or `make` only
        rebuild the targets whose inputs changed.
        """
        forked = Run(name or f"{self.name}-fork", cache=self.cache, root=self.root)
        with forked:
            pipeline_fn(**new_kwargs)
        return forked

    def __repr__(self) -> str:
        return f"<Run {self.run_id} nodes={len(self.nodes)}>"


def step(func: Optional[Callable] = None, *, cache: Optional[Cache] = None):
    """Decorator that turns a plain function into a cached, tracked step.

    Every call is:
      1. Hashed from (source code of the function + argument values, or
         upstream node hashes for arguments that are themselves the
         traced output of another step).
      2. Looked up in the cache — on a hit, the cached output is
         returned immediately with zero re-execution.
      3. On a miss, executed normally, cached, and recorded.
    """

    def decorator(f: Callable) -> Callable:
        source_hash = hashing.hash_source(f)

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            run = current_run()
            active_cache = cache or (run.cache if run is not None else default_cache())

            node_hash = hashing.hash_node(f.__qualname__, source_hash, args, kwargs)
            parents = [
                n.node_hash
                for n in (get_node(a) for a in list(args) + list(kwargs.values()))
                if n is not None
            ]

            entry = active_cache.get(node_hash)
            if entry is not None:
                output = entry.output          # already clean (unwrapped)
                cache_hit = True
                duration = 0.0
                time_saved = float(entry.metadata.get("duration_s", 0.0))
                clean_output = output
            else:
                # Unwrap arguments before calling the function
                call_args = tuple(_unwrap(a) for a in args)
                call_kwargs = {k: _unwrap(v) for k, v in kwargs.items()}
                t0 = time.time()
                raw_output = f(*call_args, **call_kwargs)
                duration = time.time() - t0

                # Recursively unwrap any traced objects to get a clean, pickleable value
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

            # Create the Node object (for both cache hit and miss)
            node = Node(
                node_hash=node_hash,
                step_name=f.__qualname__,
                parents=parents,
                cache_hit=cache_hit,
                duration_s=duration,
                time_saved_s=time_saved,
                timestamp=time.time(),
                args_repr=_safe_repr(args),
                kwargs_repr=_safe_repr(kwargs),
                output_repr=_safe_repr(clean_output),
            )

            if run is not None:
                run.record(node)

            # Attach the node to the clean output and return traced version
            return attach_node(clean_output, node)

        wrapper._loom_step = True  # type: ignore[attr-defined]
        wrapper._loom_source_hash = source_hash  # type: ignore[attr-defined]
        wrapper.__wrapped_func__ = f  # type: ignore[attr-defined]
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator