"""Content-addressed cache backends.

Loom stores every step's output under a key derived purely from its
content hash — the same idea as Git's object store or Bazel's action
cache. Two runs (even in different processes, on different days, on
different machines sharing this cache) that produce the same hash will
transparently share the same cached output.

`Cache` is a tiny abstract interface so alternate backends (Redis, S3,
a shared network drive for a team) can be dropped in later without
touching the rest of Loom.
"""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union


@dataclass
class CacheEntry:
    output: Any
    metadata: dict


class Cache:
    """Abstract cache interface. Subclass to plug in Redis/S3/etc."""

    def get(self, key: str) -> Optional[CacheEntry]:
        raise NotImplementedError

    def put(self, key: str, output: Any, metadata: dict) -> None:
        raise NotImplementedError

    def stats(self) -> dict:
        raise NotImplementedError


class DiskCache(Cache):
    """Default local cache: `<root>/objects/<hash[:2]>/<hash>.pkl`.

    Sharding by the first two hex characters keeps any one directory
    from accumulating too many files, the same trick Git uses for its
    object store.
    """

    def __init__(self, root: Union[str, Path] = ".loom_cache"):
        self.root = Path(root)
        self.objects_dir = self.root / "objects"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0

    def _paths(self, key: str):
        shard = self.objects_dir / key[:2]
        shard.mkdir(parents=True, exist_ok=True)
        return shard / f"{key}.pkl", shard / f"{key}.json"

    def get(self, key: str) -> Optional[CacheEntry]:
        data_path, meta_path = self._paths(key)
        if not data_path.exists():
            self._misses += 1
            return None

        # Remove empty or corrupted files
        if data_path.stat().st_size == 0:
            data_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            self._misses += 1
            return None

        try:
            with open(data_path, "rb") as f:
                output = pickle.load(f)
        except (EOFError, pickle.UnpicklingError, Exception):
            # Corrupt file – delete it and treat as a miss
            data_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            self._misses += 1
            return None

        self._hits += 1
        metadata = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text())
            except Exception:
                metadata = {}
        return CacheEntry(output=output, metadata=metadata)

    def put(self, key: str, output: Any, metadata: dict) -> None:
        data_path, meta_path = self._paths(key)
        with open(data_path, "wb") as f:
            pickle.dump(output, f)
        meta_path.write_text(json.dumps(metadata, indent=2, default=str))

    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total else 0.0
        return {"hits": self._hits, "misses": self._misses, "hit_rate": hit_rate}


_default_cache: Optional[DiskCache] = None


def default_cache() -> DiskCache:
    global _default_cache
    if _default_cache is None:
        _default_cache = DiskCache()
    return _default_cache