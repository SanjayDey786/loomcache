import pickle
import tempfile
from pathlib import Path

import pytest

# Skip if dependencies not installed
try:
    import boto3
    from moto import mock_aws
except ImportError:
    boto3 = None
    mock_aws = None

try:
    import redis
    import fakeredis
except ImportError:
    redis = None
    fakeredis = None

from loom.cache_remote import S3Cache, RedisCache
from loom.cache import CacheEntry


@pytest.mark.skipif(boto3 is None or mock_aws is None, reason="boto3/moto not installed")
def test_s3_cache_roundtrip():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        cache = S3Cache(bucket="test-bucket", prefix="loom/")
        assert cache.get("missing") is None

        cache.put("mykey", {"foo": "bar"}, metadata={"step": "test"})
        entry = cache.get("mykey")
        assert entry is not None
        assert entry.output == {"foo": "bar"}
        assert entry.metadata["step"] == "test"

        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1


@pytest.mark.skipif(redis is None or fakeredis is None, reason="redis/fakeredis not installed")
def test_redis_cache_roundtrip():
    # Use fakeredis in-memory server
    from fakeredis import FakeRedis
    redis_client = FakeRedis()
    # Patch the RedisCache to use this client for testing
    class TestRedisCache(RedisCache):
        def __init__(self, client, key_prefix="loom:"):
            self.redis = client
            self.key_prefix = key_prefix
            self._hits = 0
            self._misses = 0

    cache = TestRedisCache(redis_client)
    cache.put("k", 42, metadata={"type": "int"})
    entry = cache.get("k")
    assert entry.output == 42
    assert entry.metadata["type"] == "int"
    assert cache.get("missing") is None
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1