"""Node-level diffing between two runs.

See exactly *where* two pipeline executions first diverge — not just
whether their final outputs differ.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .run import Run, Node


@dataclass
class NodeDiff:
    index: int
    step_name: str
    status: str  # "same" | "changed" | "only_in_a" | "only_in_b"
    node_a: Optional[Node]
    node_b: Optional[Node]


def diff_runs(run_a: Run, run_b: Run) -> List[NodeDiff]:
    """Compare two runs node-by-node, in call order."""
    diffs: List[NodeDiff] = []
    max_len = max(len(run_a.nodes), len(run_b.nodes))
    for i in range(max_len):
        na = run_a.nodes[i] if i < len(run_a.nodes) else None
        nb = run_b.nodes[i] if i < len(run_b.nodes) else None
        if na is None:
            diffs.append(NodeDiff(i, nb.step_name, "only_in_b", na, nb))
        elif nb is None:
            diffs.append(NodeDiff(i, na.step_name, "only_in_a", na, nb))
        elif na.node_hash == nb.node_hash:
            diffs.append(NodeDiff(i, na.step_name, "same", na, nb))
        else:
            diffs.append(NodeDiff(i, na.step_name, "changed", na, nb))
    return diffs


def first_divergence(run_a: Run, run_b: Run) -> Optional[NodeDiff]:
    """The earliest node (in call order) where the two runs differ, or
    None if they are identical."""
    for d in diff_runs(run_a, run_b):
        if d.status != "same":
            return d
    return None


def format_diff(diffs: List[NodeDiff]) -> str:
    symbols = {"same": " ", "changed": "~", "only_in_a": "-", "only_in_b": "+"}
    lines = []
    for d in diffs:
        lines.append(f"{symbols[d.status]} [{d.index}] {d.step_name}  ({d.status})")
        if d.status == "changed":
            lines.append(f"      a: {d.node_a.output_repr}")
            lines.append(f"      b: {d.node_b.output_repr}")
    return "\n".join(lines)