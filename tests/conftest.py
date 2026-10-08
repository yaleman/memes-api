"""Isolated real S3 backing store for application tests."""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from testcontainers.community.localstack import LocalStackContainer

# Set before test collection imports the application; never load user credentials.
os.environ["MEMES_API_CONFIG"] = str(Path(__file__).with_name("test_config.json"))


@pytest.fixture(scope="session")
def localstack() -> Iterator[Any]:
    with LocalStackContainer(
        "localstack/localstack:4.14.0", region_name="us-east-1"
    ).with_services("s3") as container:
        yield container


@pytest.fixture
def storage(
    localstack: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Any]:
    import memes_api
    from memes_api.config import MemeConfig

    client = localstack.get_client(
        "s3", aws_access_key_id="test", aws_secret_access_key="test"
    )
    bucket = "memes-test-" + uuid4().hex
    client.create_bucket(Bucket=bucket)
    config = MemeConfig(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_region="us-east-1",
        bucket=bucket,
        endpoint_url=localstack.get_url(),
        baseurl="http://testserver",
        thumbnail_cache_dir=tmp_path / "thumbnails",
    )
    monkeypatch.setattr(memes_api, "meme_config", config)
    memes_api.meme_cache.clear()
    yield client
    objects = client.list_objects_v2(Bucket=bucket).get("Contents", [])
    if objects:
        client.delete_objects(
            Bucket=bucket, Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]}
        )
    client.delete_bucket(Bucket=bucket)
    memes_api.meme_cache.clear()
