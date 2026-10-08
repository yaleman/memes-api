"""Persistent thumbnails and coordinated background storage work."""

import asyncio
import logging
import tempfile
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from enum import Enum, auto
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError

from .config import MemeConfig
from .constants import THUMBNAIL_BUCKET_PREFIX
from .sessions import get_aioboto3_session
from .thumbnails import generate_thumbnail
from .utils import save_thumbnail

CACHE_CONTROL = "public, max-age=86400"
MAX_AGE = 86400
LOGGER = logging.getLogger(__name__)


class CacheKind(Enum):
    FRESH = auto()
    STALE = auto()
    MISS = auto()
    ERROR = auto()


class FailureKind(Enum):
    MISSING = auto()
    STORAGE = auto()
    INVALID_IMAGE = auto()


@dataclass(frozen=True)
class CacheLookup:
    kind: CacheKind
    path: Path


@dataclass(frozen=True)
class CachedThumbnail:
    path: Path


@dataclass(frozen=True)
class MemoryThumbnail:
    content: bytes


@dataclass(frozen=True)
class ThumbnailFailure:
    kind: FailureKind


ThumbnailResult = CachedThumbnail | MemoryThumbnail | ThumbnailFailure


def missing_object(error: ClientError) -> bool:
    """Classify the structured S3 error, never its rendered message."""
    return error.response.get("Error", {}).get("Code") in {
        "NoSuchKey",
        "404",
        "NotFound",
    }


class ThumbnailCache:
    """One cache per application lifespan; S3 remains the source of truth."""

    def __init__(self, config: MemeConfig) -> None:
        self.config = config
        self.directory = config.thumbnail_cache_dir.expanduser()
        self.loads: dict[str, asyncio.Task[ThumbnailResult]] = {}
        self.tasks: set[asyncio.Task[Any]] = set()
        self.slots = asyncio.Semaphore(4)

    def path(self, filename: str) -> Path:
        identity = repr((self.config.bucket, self.config.endpoint_url, filename))
        return self.directory / (sha256(identity.encode()).hexdigest() + ".jpg")

    def lookup(self, filename: str) -> CacheLookup:
        path = self.path(filename)
        try:
            modified = path.stat().st_mtime
            # An unreadable or non-file entry must fall back to storage.
            with path.open("rb"):
                pass
        except FileNotFoundError:
            return CacheLookup(CacheKind.MISS, path)
        except OSError:
            LOGGER.exception("Cannot inspect thumbnail cache")
            return CacheLookup(CacheKind.ERROR, path)
        kind = CacheKind.FRESH if time.time() - modified < MAX_AGE else CacheKind.STALE
        return CacheLookup(kind, path)

    def write(self, filename: str, content: bytes) -> ThumbnailResult:
        path = self.path(filename)
        temporary: Path | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=self.directory, delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(content)
            temporary.replace(path)
            return CachedThumbnail(path)
        except OSError:
            LOGGER.exception("Cannot persist thumbnail cache")
            return MemoryThumbnail(content)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    LOGGER.exception("Cannot clean up temporary thumbnail")

    def remove(self, filename: str) -> None:
        try:
            self.path(filename).unlink(missing_ok=True)
        except OSError:
            LOGGER.exception("Cannot remove missing thumbnail from cache")

    def start(self, work: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(work)
        self.tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            LOGGER.error("Thumbnail background work failed", exc_info=task.exception())

    async def close(self) -> None:
        while self.tasks:
            tasks = list(self.tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def get(self, filename: str) -> ThumbnailResult:
        entry = await asyncio.to_thread(self.lookup, filename)
        match entry.kind:
            case CacheKind.FRESH:
                return CachedThumbnail(entry.path)
            case CacheKind.STALE:
                # Snapshot before refresh can replace or remove the stale file.
                try:
                    content = await asyncio.to_thread(entry.path.read_bytes)
                except OSError:
                    LOGGER.exception("Cannot read stale thumbnail cache")
                    return await self.load(filename)
                self.start(self.load(filename))
                return MemoryThumbnail(content)
            case CacheKind.MISS | CacheKind.ERROR:
                return await self.load(filename)

    async def load(self, filename: str, client: Any = None) -> ThumbnailResult:
        if filename not in self.loads:
            task: asyncio.Task[ThumbnailResult] = self.start(
                self._load(filename, client)
            )
            self.loads[filename] = task
            task.add_done_callback(lambda done: self.loads.pop(filename, None))
        return await asyncio.shield(self.loads[filename])

    async def _load(self, filename: str, client: Any) -> ThumbnailResult:
        async with self.slots:
            entry = await asyncio.to_thread(self.lookup, filename)
            if entry.kind is CacheKind.FRESH:
                return CachedThumbnail(entry.path)
            if client is not None:
                return await self._fetch(filename, client)
            async with get_aioboto3_session(self.config).client(
                "s3", endpoint_url=self.config.endpoint_url
            ) as storage:
                return await self._fetch(filename, storage)

    async def _fetch(self, filename: str, client: Any) -> ThumbnailResult:
        try:
            try:
                obj = await client.get_object(
                    Bucket=self.config.bucket, Key=THUMBNAIL_BUCKET_PREFIX + filename
                )
                async with obj["Body"] as body:
                    content = await body.read()
            except ClientError as error:
                if not missing_object(error):
                    raise
                obj = await client.get_object(Bucket=self.config.bucket, Key=filename)
                async with obj["Body"] as body:
                    original = await body.read()
                try:
                    content = await asyncio.to_thread(generate_thumbnail, original)
                except (
                    Image.DecompressionBombError,
                    UnidentifiedImageError,
                    OSError,
                    ValueError,
                ):
                    LOGGER.exception("Cannot decode thumbnail source")
                    return ThumbnailFailure(FailureKind.INVALID_IMAGE)
                self.start(self._upload(filename, content))
            return await asyncio.to_thread(self.write, filename, content)
        except ClientError as error:
            if missing_object(error):
                await asyncio.to_thread(self.remove, filename)
                return ThumbnailFailure(FailureKind.MISSING)
            LOGGER.exception("Thumbnail storage request failed")
            return ThumbnailFailure(FailureKind.STORAGE)
        except (BotoCoreError, OSError):
            LOGGER.exception("Thumbnail storage connection failed")
            return ThumbnailFailure(FailureKind.STORAGE)

    async def _upload(self, filename: str, content: bytes) -> None:
        async with (
            self.slots,
            get_aioboto3_session(self.config).client(
                "s3", endpoint_url=self.config.endpoint_url
            ) as client,
        ):
            await save_thumbnail(client, filename, BytesIO(content), self.config)

    async def prewarm(self, filenames: list[str]) -> None:
        async with get_aioboto3_session(self.config).client(
            "s3", endpoint_url=self.config.endpoint_url
        ) as client:
            # A fixed number of workers also bounds task count for large buckets.
            pending = iter(filenames)

            async def worker() -> None:
                for filename in pending:
                    entry = await asyncio.to_thread(self.lookup, filename)
                    if entry.kind is not CacheKind.FRESH:
                        await self.load(filename, client)

            workers = [asyncio.create_task(worker()) for _ in range(4)]
            try:
                await asyncio.gather(*workers)
            finally:
                for worker_task in workers:
                    worker_task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)

    def response(self, result: CachedThumbnail | MemoryThumbnail) -> Response:
        headers = {"Cache-Control": CACHE_CONTROL}
        match result:
            case CachedThumbnail(path):
                return FileResponse(path, media_type="image/jpeg", headers=headers)
            case MemoryThumbnail(content):
                headers["ETag"] = '"' + sha256(content).hexdigest() + '"'
                return Response(content, media_type="image/jpeg", headers=headers)
