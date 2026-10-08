"""Cache integration tests using real LocalStack S3 operations."""

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

import memes_api
from memes_api import app
from memes_api.constants import THUMBNAIL_BUCKET_PREFIX
from memes_api.thumbnail_cache import (
    CachedThumbnail,
    CacheKind,
    FailureKind,
    MemoryThumbnail,
    ThumbnailCache,
    ThumbnailFailure,
)
from tests.test_endpoints import seed


async def drain(cache: ThumbnailCache) -> None:
    while cache.tasks:
        await asyncio.gather(*list(cache.tasks))


def test_generation_and_upload(storage: Any) -> None:
    seed(storage)

    async def scenario() -> None:
        cache = ThumbnailCache(memes_api.meme_config)
        result = await cache.get("robot.jpg")
        assert isinstance(result, CachedThumbnail)
        response = cache.response(result)
        assert response.media_type == "image/jpeg"
        assert response.headers["cache-control"] == "public, max-age=86400"
        await drain(cache)
        remote = storage.get_object(
            Bucket=memes_api.meme_config.bucket,
            Key=THUMBNAIL_BUCKET_PREFIX + "robot.jpg",
        )
        assert remote["Body"].read() == result.path.read_bytes()
        assert remote["ContentType"] == "image/jpeg"
        assert remote["CacheControl"] == "public, max-age=86400"
        await cache.close()

    asyncio.run(scenario())


def test_prewarm_restart_and_unavailable_storage(
    storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = seed(storage, thumbnail=True)

    async def scenario() -> None:
        cache = ThumbnailCache(memes_api.meme_config)
        await cache.prewarm(["robot.jpg"])
        assert cache.lookup("robot.jpg").kind is CacheKind.FRESH
        await cache.close()

    asyncio.run(scenario())

    async def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("A disk hit must not access S3")

    monkeypatch.setattr(ThumbnailCache, "_fetch", unavailable)
    # A new lifespan recreates the cache and prewarmer with the same directory.
    with TestClient(app) as client:
        started = time.perf_counter()
        response = client.get("/thumbnail/robot.jpg")
        elapsed = time.perf_counter() - started
        assert response.content == expected
        assert elapsed < 0.1
        print(f"Warm thumbnail HTTP response: {elapsed * 1000:.2f} ms")


def test_concurrent_loads(storage: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    seed(storage)
    original = ThumbnailCache._fetch
    calls = 0

    async def counted(self: ThumbnailCache, filename: str, client: Any) -> Any:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return await original(self, filename, client)

    monkeypatch.setattr(ThumbnailCache, "_fetch", counted)

    async def scenario() -> None:
        cache = ThumbnailCache(memes_api.meme_config)
        results = await asyncio.gather(*[cache.get("robot.jpg") for _ in range(15)])
        assert all(isinstance(result, CachedThumbnail) for result in results)
        assert calls == 1
        await cache.close()

    asyncio.run(scenario())


def test_stale_refresh_and_deletion(storage: Any) -> None:
    expected = seed(storage, thumbnail=True)

    async def scenario() -> None:
        cache = ThumbnailCache(memes_api.meme_config)
        await cache.get("robot.jpg")
        path = cache.path("robot.jpg")
        old = time.time() - 86401
        os.utime(path, (old, old))
        replacement = expected + b"new-version"
        storage.put_object(
            Bucket=memes_api.meme_config.bucket,
            Key=THUMBNAIL_BUCKET_PREFIX + "robot.jpg",
            Body=replacement,
        )
        stale = await cache.get("robot.jpg")
        assert isinstance(stale, MemoryThumbnail)
        assert stale.content == expected
        await drain(cache)
        assert path.read_bytes() == replacement
        assert cache.lookup("robot.jpg").kind is CacheKind.FRESH
        storage.delete_object(Bucket=memes_api.meme_config.bucket, Key="robot.jpg")
        storage.delete_object(
            Bucket=memes_api.meme_config.bucket,
            Key=THUMBNAIL_BUCKET_PREFIX + "robot.jpg",
        )
        os.utime(path, (old, old))
        assert isinstance(await cache.get("robot.jpg"), MemoryThumbnail)
        await drain(cache)
        assert not path.exists()
        assert await cache.get("robot.jpg") == ThumbnailFailure(FailureKind.MISSING)
        await cache.close()

    asyncio.run(scenario())


def test_transient_failure_retains_stale(
    storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = seed(storage, thumbnail=True)

    async def scenario() -> None:
        cache = ThumbnailCache(memes_api.meme_config)
        await cache.get("robot.jpg")
        path = cache.path("robot.jpg")
        old = time.time() - 86401
        os.utime(path, (old, old))

        class FailingClient:
            async def get_object(self, **kwargs: Any) -> Any:
                raise ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")

        result = await cache._fetch("robot.jpg", FailingClient())
        assert result == ThumbnailFailure(FailureKind.STORAGE)
        assert path.read_bytes() == expected
        original = ThumbnailCache._fetch
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed(self: ThumbnailCache, filename: str, client: Any) -> Any:
            entered.set()
            await release.wait()
            return await original(self, filename, FailingClient())

        monkeypatch.setattr(ThumbnailCache, "_fetch", delayed)
        started = time.perf_counter()
        assert isinstance(await cache.get("robot.jpg"), MemoryThumbnail)
        assert time.perf_counter() - started < 0.1
        await asyncio.wait_for(entered.wait(), timeout=5)
        release.set()
        await drain(cache)
        assert path.read_bytes() == expected
        await cache.close()

    asyncio.run(scenario())


def test_unsafe_keys_and_unwritable_cache(storage: Any, tmp_path: Path) -> None:
    filename = "../../outside.jpg"
    expected = seed(storage, filename, thumbnail=True)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("blocked")
    config = memes_api.meme_config.model_copy(update={"thumbnail_cache_dir": blocked})

    async def scenario() -> None:
        cache = ThumbnailCache(config)
        assert cache.path(filename).parent == blocked
        result = await cache.get(filename)
        assert isinstance(result, MemoryThumbnail)
        assert result.content == expected
        response = cache.response(result)
        assert response.headers["content-type"] == "image/jpeg"
        assert int(response.headers["content-length"]) == len(expected)
        assert response.headers["etag"]
        assert not (tmp_path.parent / "outside.jpg").exists()
        await cache.close()

    asyncio.run(scenario())


def test_shutdown_cancels_work(storage: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    seed(storage, thumbnail=True)

    async def scenario() -> None:
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocked(self: ThumbnailCache, filename: str, client: Any) -> Any:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(ThumbnailCache, "_fetch", blocked)
        cache = ThumbnailCache(memes_api.meme_config)
        cache.start(cache.prewarm(["robot.jpg"]))
        await asyncio.wait_for(entered.wait(), timeout=5)
        await asyncio.wait_for(cache.close(), timeout=5)
        assert cancelled.is_set()
        assert not cache.tasks
        assert not cache.loads

    asyncio.run(scenario())


def test_invalid_source(storage: Any) -> None:
    storage.put_object(
        Bucket=memes_api.meme_config.bucket, Key="bad.jpg", Body=b"not an image"
    )
    with TestClient(app) as client:
        assert client.get("/thumbnail/bad.jpg").status_code == 503


def test_prewarm_bounds_concurrency(
    storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    filenames = [f"robot-{index}.jpg" for index in range(8)]
    for filename in filenames:
        seed(storage, filename, thumbnail=True)
    original = ThumbnailCache._fetch
    active = 0
    peak = 0
    clients: set[int] = set()

    async def measured(self: ThumbnailCache, filename: str, client: Any) -> Any:
        nonlocal active, peak
        clients.add(id(client))
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.02)
            return await original(self, filename, client)
        finally:
            active -= 1

    monkeypatch.setattr(ThumbnailCache, "_fetch", measured)

    async def scenario() -> None:
        cache = ThumbnailCache(memes_api.meme_config)
        await cache.prewarm(filenames)
        assert peak == 4
        assert len(clients) == 1
        assert all(cache.lookup(name).kind is CacheKind.FRESH for name in filenames)
        await cache.close()

    asyncio.run(scenario())


def test_non_file_cache_entry_falls_back(storage: Any) -> None:
    expected = seed(storage, thumbnail=True)

    async def scenario() -> None:
        cache = ThumbnailCache(memes_api.meme_config)
        cache.path("robot.jpg").mkdir(parents=True)
        assert cache.lookup("robot.jpg").kind is CacheKind.ERROR
        result = await cache.get("robot.jpg")
        assert isinstance(result, MemoryThumbnail)
        assert result.content == expected
        assert list(cache.directory.iterdir()) == [cache.path("robot.jpg")]
        await cache.close()

    asyncio.run(scenario())
