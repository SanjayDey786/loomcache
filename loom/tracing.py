"""Transparent value wrapping so Loom can track data lineage.

When a @step function returns a value, Loom attaches an invisible
`_loom_node` marker to it. If that value is later passed into another
@step call, Loom sees the marker and knows there is a dependency edge
between the two nodes — without requiring the user to declare any
dependencies manually. This is what lets a plain chain of Python
function calls become a real, hashable DAG.
"""
from __future__ import annotations

from typing import Any

_TRACED_SUBCLASS_CACHE: dict = {}


def _traced_subclass(base: type) -> type:
    if base in _TRACED_SUBCLASS_CACHE:
        return _TRACED_SUBCLASS_CACHE[base]

    class _Traced(base):  # type: ignore[misc,valid-type]
        __slots__ = ("_loom_node",)

    _Traced.__name__ = f"Traced{base.__name__.capitalize()}"
    _TRACED_SUBCLASS_CACHE[base] = _Traced
    return _Traced


class TracedBox:
    """Fallback wrapper for values that can't be subclassed or tagged
    directly (e.g. `bool`, or some C-extension objects).

    Behaves like the wrapped value for repr/equality/truthiness/hash,
    and transparently forwards attribute access, so downstream code can
    usually treat it exactly like the original object. Call `.unwrap()`
    to get the raw value back explicitly.
    """

    __slots__ = ("_loom_value", "_loom_node")

    def __init__(self, value: Any, node: Any):
        object.__setattr__(self, "_loom_value", value)
        object.__setattr__(self, "_loom_node", node)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_loom_value"), name)

    def __repr__(self):
        return repr(object.__getattribute__(self, "_loom_value"))

    def __str__(self):
        return str(object.__getattribute__(self, "_loom_value"))

    def __eq__(self, other):
        return object.__getattribute__(self, "_loom_value") == other

    def __hash__(self):
        return hash(object.__getattribute__(self, "_loom_value"))

    def __bool__(self):
        return bool(object.__getattribute__(self, "_loom_value"))

    def unwrap(self):
        return object.__getattribute__(self, "_loom_value")


# CPython allows adding `__slots__` to subclasses of `str`, `tuple`, and
# `frozenset` (their C layout has room for it), but NOT to subclasses of
# `int` or `float` (fixed-size numeric layout, no room for extra slots) --
# those go through `TracedBox` instead, same as `bool`.
_DIRECTLY_TAGGABLE_IMMUTABLES = (str, tuple, frozenset)
_DIRECTLY_TAGGABLE_MUTABLES = (list, dict, set)


def attach_node(value: Any, node: Any) -> Any:
    """Attach a lineage marker to `value`, returning a traced version of it.

    Supports directly: str, tuple, frozenset, list, dict, set, and any
    plain object with a `__dict__`. Everything else (notably `int`,
    `float`, and `bool`, whose fixed C layout doesn't allow extra
    attributes) falls back to the transparent `TracedBox` wrapper.
    """
    if getattr(value, "_loom_node", None) is not None:
        return value  # already traced (e.g. a step just returns its input)

    cls = type(value)

    if cls in _DIRECTLY_TAGGABLE_IMMUTABLES or cls in _DIRECTLY_TAGGABLE_MUTABLES:
        traced_cls = _traced_subclass(cls)
        obj = traced_cls(value)
        object.__setattr__(obj, "_loom_node", node)
        return obj

    try:
        object.__setattr__(value, "_loom_node", node)
        return value
    except (AttributeError, TypeError):
        pass

    return TracedBox(value, node)


def get_node(value: Any):
    return getattr(value, "_loom_node", None)


def unwrap(value: Any) -> Any:
    if isinstance(value, TracedBox):
        return value.unwrap()
    return value


def unwrap_recursive(value: Any) -> Any:
    """Recursively remove all Loom tracing from a value, returning a plain Python object."""
    if hasattr(value, "_loom_node"):
        # It's a traced object. Convert to its base type.
        if isinstance(value, TracedBox):
            return unwrap_recursive(value.unwrap())
        else:
            # Subclass of built‑in (e.g., TracedStr). Get the base class and convert.
            base = value.__class__.__base__
            try:
                return unwrap_recursive(base(value))
            except Exception:
                # Fallback – return the value as‑is (might still break pickle)
                return value
    elif isinstance(value, dict):
        return {unwrap_recursive(k): unwrap_recursive(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple, set, frozenset)):
        return type(value)(unwrap_recursive(v) for v in value)
    else:
        return value