"""Alias module: `from loom import trace` then use `trace.step`, `trace.Run`.

Purely a namespacing convenience some people prefer stylistically —
identical in behavior to importing `step` / `Run` from `loom` directly.

    from loom import trace

    @trace.step
    def plan(query: str) -> str:
        ...

    with trace.Run("my-pipeline") as run:
        ...
"""
from .run import Node, Run, current_run, step  # noqa: F401