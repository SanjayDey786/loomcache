"""Content-addressed hashing utilities for Loom.

Every cache key in Loom is derived deterministically from:
  1. The *source code* of the step function (so editing a prompt
     invalidates the cache automatically).
  2. The values (or upstream node hashes) of every argument.

This mirrors how Bazel/Nix key build outputs off content instead of
timestamps, and is the reason Loom can safely skip re-running a step.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import pickle
from typing import Any, Callable, Optional


def _stable_json(value: Any) -> Optional[str]:
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None


def hash_value(value: Any) -> str:
    """Return a stable content hash for an arbitrary Python value.

    If `value` is itself the traced output of an upstream step, its
    identity for hashing purposes IS the upstream node's hash — this is
    what turns a chain of step calls into a real dependency graph.

    Otherwise: try JSON first (fast, stable across processes and
    machines), fall back to pickle bytes, and finally to repr() for
    exotic objects that are neither JSON-serializable nor picklable.
    """
    node = getattr(value, "_loom_node", None)
    if node is not None:
        return f"node:{node.node_hash}"

    as_json = _stable_json(value)
    if as_json is not None:
        payload = f"json:{as_json}".encode()
    else:
        try:
            payload = b"pickle:" + pickle.dumps(value)
        except Exception:
            payload = f"repr:{value!r}".encode()
    return hashlib.sha256(payload).hexdigest()


def hash_source(func: Callable) -> str:
    """Hash the source code of a function.

    If the function body changes (e.g. you tweak a prompt template),
    this hash changes, which changes every node hash downstream of it —
    Loom will correctly recompute rather than serve a stale cache hit.
    """
    try:
        src = inspect.getsource(func)
    except (OSError, TypeError):
        src = f"{func.__module__}.{func.__qualname__}"
    return hashlib.sha256(src.encode()).hexdigest()


def hash_node(
    step_name: str,
    source_hash: str,
    args: tuple,
    kwargs: dict,
    extra: str = "",
) -> str:
    """Combine step identity + source + argument hashes into one node hash."""
    parts = [f"step:{step_name}", f"src:{source_hash}"]
    for a in args:
        parts.append(f"arg:{hash_value(a)}")
    for k in sorted(kwargs):
        parts.append(f"kw:{k}={hash_value(kwargs[k])}")
    if extra:
        parts.append(f"extra:{extra}")
    payload = "|".join(parts).encode()
    return hashlib.sha256(payload).hexdigest()