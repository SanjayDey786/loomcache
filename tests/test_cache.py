import tempfile
from pathlib import Path

from loom.cache import DiskCache


def test_disk_cache_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=Path(tmp) / "cache")
        assert cache.get("abc") is None
        cache.put("abc", {"hello": "world"}, metadata={"step_name": "test"})
        entry = cache.get("abc")
        assert entry is not None
        assert entry.output == {"hello": "world"}
        assert entry.metadata["step_name"] == "test"


def test_disk_cache_stats_track_hits_and_misses():
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(root=Path(tmp) / "cache")
        cache.get("missing")
        cache.put("key", "value", {})
        cache.get("key")
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


def test_disk_cache_persists_across_instances():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "cache"
        DiskCache(root=root).put("k", [1, 2, 3], {})
        reopened = DiskCache(root=root)
        entry = reopened.get("k")
        assert entry.output == [1, 2, 3]
