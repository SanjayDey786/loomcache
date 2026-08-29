"""Loom: a content-addressed, deterministic replay engine for agent AI workflows."""

from .cache import Cache, DiskCache, default_cache
from .diff import diff_runs, first_divergence, format_diff
from .run import Node, Run, current_run, step
from .tracing import TracedBox, get_node, attach_node, unwrap, unwrap_recursive

# Optional extensions – if dependencies are missing, these imports are skipped.
try:
    from .cache_remote import S3Cache, RedisCache
except ImportError:
    S3Cache = RedisCache = None

try:
    from .langchain import wrap_runnable, CachedRunnable
except ImportError:
    wrap_runnable = CachedRunnable = None

try:
    from .async_run import AsyncRun, async_step, gather
except ImportError:
    AsyncRun = async_step = gather = None

__version__ = "1.0.0"

__all__ = [
    "step",
    "Run",
    "Node",
    "current_run",
    "Cache",
    "DiskCache",
    "default_cache",
    "diff_runs",
    "first_divergence",
    "format_diff",
    "get_node",
    "attach_node",
    "unwrap",
    "unwrap_recursive",
    "TracedBox",
    "S3Cache",
    "RedisCache",
    "wrap_runnable",
    "CachedRunnable",
    "AsyncRun",
    "async_step",
    "gather",
]