"""Remote cache backends: S3 and Redis.

To use, install the corresponding extra:

    pip install loomtrace[s3]   # for S3
    pip install loomtrace[redis]  # for Redis
"""

from __future__ import annotations

import json
import pickle
from typing import Any, Optional

from .cache import Cache, CacheEntry


class S3Cache(Cache):
    """Amazon S3 cache backend.

    Args:
        bucket: S3 bucket name.
        prefix: Key prefix (e.g., "loom_cache/").
        region_name: AWS region, optional.
        aws_access_key_id, aws_secret_access_key: Optional credentials.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "loom_cache/",
        region_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        try:
            import boto3
        except ImportError as exc:
            raise ImportError("Install boto3: pip install loomtrace[s3]") from exc

        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"
        self.s3 = boto3.client(
            "s3",
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        self._hits = 0
        self._misses = 0

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key[:2]}/{key}.pkl"

    def _meta_key(self, key: str) -> str:
        return f"{self.prefix}{key[:2]}/{key}.json"

    def get(self, key: str) -> Optional[CacheEntry]:
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=self._key(key))
            output = pickle.loads(obj["Body"].read())
        except self.s3.exceptions.NoSuchKey:
            self._misses += 1
            return None

        self._hits += 1
        metadata = {}
        try:
            meta_obj = self.s3.get_object(Bucket=self.bucket, Key=self._meta_key(key))
            metadata = json.loads(meta_obj["Body"].read().decode())
        except self.s3.exceptions.NoSuchKey:
            pass

        return CacheEntry(output=output, metadata=metadata)

    def put(self, key: str, output: Any, metadata: dict) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=self._key(key),
            Body=pickle.dumps(output),
        )
        self.s3.put_object(
            Bucket=self.bucket,
            Key=self._meta_key(key),
            Body=json.dumps(metadata).encode(),
        )

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
        }


class RedisCache(Cache):
    """Redis cache backend.

    Args:
        url: Redis URL (e.g., redis://localhost:6379/0).
        key_prefix: Prefix for all keys.
    """

    def __init__(self, url: str = "redis://localhost:6379/0", key_prefix: str = "loom:"):
        try:
            import redis
        except ImportError as exc:
            raise ImportError("Install redis-py: pip install loomtrace[redis]") from exc

        self.redis = redis.from_url(url)
        self.key_prefix = key_prefix
        self._hits = 0
        self._misses = 0

    def _data_key(self, key: str) -> str:
        return f"{self.key_prefix}{key}:data"

    def _meta_key(self, key: str) -> str:
        return f"{self.key_prefix}{key}:meta"

    def get(self, key: str) -> Optional[CacheEntry]:
        data = self.redis.get(self._data_key(key))
        if data is None:
            self._misses += 1
            return None
        self._hits += 1
        output = pickle.loads(data)
        meta = self.redis.get(self._meta_key(key))
        metadata = json.loads(meta) if meta else {}
        return CacheEntry(output=output, metadata=metadata)

    def put(self, key: str, output: Any, metadata: dict) -> None:
        self.redis.set(self._data_key(key), pickle.dumps(output))
        self.redis.set(self._meta_key(key), json.dumps(metadata))

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
        }