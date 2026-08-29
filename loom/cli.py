"""Command-line interface for Loom.

    loom show <run.json>
    loom diff <run_a.json> <run_b.json>
    loom stats <run.json>
    loom web [--runs-dir DIR] [--host HOST] [--port PORT]
"""
from __future__ import annotations

import argparse

from .diff import diff_runs, format_diff
from .run import Run


def cmd_show(args):
    run = Run.load(args.run_path)
    print(f"Run: {run.name}  ({run.run_id})")
    print(f"Nodes: {len(run.nodes)}\n")
    for i, node in enumerate(run.nodes):
        tag = "HIT " if node.cache_hit else "MISS"
        print(f"[{i}] {tag}  {node.step_name}  ({node.node_hash[:10]}...)")
        print(f"      -> {node.output_repr}")
    stats = run.stats()
    print(
        f"\nCache hit rate: {stats['hit_rate']:.0%}  "
        f"({stats['cache_hits']}/{stats['total_nodes']})"
    )
    print(f"Wall time: {stats['wall_time_s']}s   Time saved by cache: {stats['time_saved_s']}s")


def cmd_diff(args):
    run_a = Run.load(args.run_a)
    run_b = Run.load(args.run_b)
    diffs = diff_runs(run_a, run_b)
    print(format_diff(diffs))
    changed = [d for d in diffs if d.status != "same"]
    if changed:
        print(
            f"\n{len(changed)} node(s) differ. First divergence: "
            f"[{changed[0].index}] {changed[0].step_name}"
        )
    else:
        print("\nRuns are identical.")


def cmd_stats(args):
    run = Run.load(args.run_path)
    for k, v in run.stats().items():
        print(f"{k}: {v}")


def cmd_web(args):
    try:
        from loom.web import serve
    except ImportError as exc:
        raise SystemExit("Install loomtrace[web] to use the web UI.") from exc
    serve(runs_dir=args.runs_dir, host=args.host, port=args.port)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="loom",
        description="Loom: content-addressed execution engine for agent workflows.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="Show all nodes in a saved run")
    p_show.add_argument("run_path")
    p_show.set_defaults(func=cmd_show)

    p_diff = sub.add_parser("diff", help="Diff two saved runs node-by-node")
    p_diff.add_argument("run_a")
    p_diff.add_argument("run_b")
    p_diff.set_defaults(func=cmd_diff)

    p_stats = sub.add_parser("stats", help="Show cache hit-rate stats for a run")
    p_stats.add_argument("run_path")
    p_stats.set_defaults(func=cmd_stats)

    p_web = sub.add_parser("web", help="Launch web UI")
    p_web.add_argument("--runs-dir", default=".loom_runs", help="Directory containing run JSONs")
    p_web.add_argument("--host", default="127.0.0.1", help="Host to bind")
    p_web.add_argument("--port", type=int, default=5000, help="Port to bind")
    p_web.set_defaults(func=cmd_web)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()