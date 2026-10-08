"""HTTP behavior against testcontainers-managed LocalStack S3."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import memes_api
from memes_api import app
from memes_api.constants import THUMBNAIL_BUCKET_PREFIX
from memes_api.thumbnails import generate_thumbnail


def seed(storage: Any, filename: str = "robot.jpg", thumbnail: bool = False) -> bytes:
    content = Path(__file__).with_name("beep-boop-i-am-a-robot.jpg").read_bytes()
    storage.put_object(
        Bucket=memes_api.meme_config.bucket,
        Key=filename,
        Body=content,
        ContentType="image/jpeg",
    )
    if thumbnail:
        content = generate_thumbnail(content)
        storage.put_object(
            Bucket=memes_api.meme_config.bucket,
            Key=THUMBNAIL_BUCKET_PREFIX + filename,
            Body=content,
            ContentType="image/jpeg",
        )
    return content


def test_homepage_and_listing(storage: Any) -> None:
    seed(storage, thumbnail=True)
    with TestClient(app, headers={"Accept-Encoding": "identity"}) as client:
        assert client.get("/").status_code == 200
        assert client.get("/allimages").json() == {"images": ["robot.jpg"]}
        assert client.get("/image_info/robot.jpg").status_code == 200


@pytest.mark.parametrize("stored", [True, False])
def test_thumbnail_headers(storage: Any, stored: bool) -> None:
    expected = seed(storage, thumbnail=stored)
    if not stored:
        expected = generate_thumbnail(expected)
    with TestClient(app, headers={"Accept-Encoding": "identity"}) as client:
        response = client.get("/thumbnail/robot.jpg")
        assert response.status_code == 200
        assert response.content == expected
        assert response.headers["content-type"] == "image/jpeg"
        assert int(response.headers["content-length"]) == len(expected)
        assert response.headers["etag"]
        assert response.headers["cache-control"] == "public, max-age=86400"


def test_original_headers(storage: Any) -> None:
    expected = seed(storage)
    with TestClient(app, headers={"Accept-Encoding": "identity"}) as client:
        response = client.get("/image/robot.jpg")
        assert response.content == expected
        assert response.headers["content-type"] == "image/jpeg"
        assert int(response.headers["content-length"]) == len(expected)
        assert response.headers["etag"]
        assert response.headers["cache-control"] == "public, max-age=86400"
        assert "content_type" not in response.headers
        assert "content_length" not in response.headers


def test_missing_objects(storage: Any) -> None:
    with TestClient(app, headers={"Accept-Encoding": "identity"}) as client:
        for route in ["thumbnail", "image", "image_info"]:
            assert client.get(f"/{route}/absent.jpg").status_code == 404


def test_static_and_openapi(storage: Any) -> None:
    with TestClient(app, headers={"Accept-Encoding": "identity"}) as client:
        for route in [
            "/openapi.json",
            "/up",
            "/robots.txt",
            "/static/js/memesapi.js",
            "/static/css/memesapi.css",
            "/static/images/icon.svg",
        ]:
            assert client.get(route).status_code == 200
        assert "/thumbnail/{filename}" in client.get("/openapi.json").json()["paths"]
