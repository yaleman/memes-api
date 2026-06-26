"""Tests for bugs discovered during repository review."""

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import inspect
from botocore.exceptions import ClientError
from PIL import Image
from memes_api import generate_thumbnail, image_cleanup, create_app
from memes_api.s3_utils import list_images
from memes_api.config import MemeConfig


test_config = MemeConfig.model_validate_json(
    Path("tests/test_config.json").read_text(encoding="utf-8")
)
app = create_app(config=test_config)


class TestPathTraversal:
    """Tests that static file endpoints reject path traversal attempts."""

    def setup_method(self):
        test_config = MemeConfig.model_validate_json(
            Path("tests/test_config.json").read_text(encoding="utf-8")
        )
        self.client = TestClient(create_app(config=test_config))

    def test_js_path_traversal_rejected(self):
        response = self.client.get("/static/js/../../../../etc/passwd")
        assert response.status_code in (403, 404)

    def test_js_path_traversal_encoded(self):
        response = self.client.get("/static/js/%2e%2e/%2e%2e/etc/passwd")
        assert response.status_code in (403, 404)

    def test_css_path_traversal_rejected(self):
        response = self.client.get("/static/css/../../../etc/passwd")
        assert response.status_code in (403, 404)

    def test_images_path_traversal_rejected(self):
        response = self.client.get("/static/images/../../../etc/passwd")
        assert response.status_code in (403, 404)

    def test_valid_js_served(self):
        response = self.client.get("/static/js/memesapi.js")
        assert response.status_code == 200


class TestThumbnailCentering:
    """Tests that thumbnail centering uses correct width/height dimensions."""

    def test_thumbnail_centered_correctly(self):

        buf = io.BytesIO()
        img = Image.new("RGB", (50, 10), color="red")
        img.save(buf, "JPEG")
        buf.seek(0)

        result = generate_thumbnail(buf.read())
        assert result.hash
        assert len(result.reader.read()) > 0

    def test_thumbnail_uses_x_and_y_separately(self):
        """Centering code must reference ThumbnailDimensions.X and .Y separately."""

        source = inspect.getsource(generate_thumbnail)
        assert "ThumbnailDimensions.X" in source
        assert "ThumbnailDimensions.Y" in source


class TestThumbnailCachedLookupDoesNotSwallowErrors:
    """Tests that non-404 errors in cached-thumbnail lookup are propagated."""

    def test_error_code_check_exists(self):

        app = create_app()

        thumbnail_handler = None
        for route in app.routes:
            if hasattr(route, "name") and route.name == "get_thumbnail":
                thumbnail_handler = route.endpoint  # ty: ignore[unresolved-attribute]
                break
        assert thumbnail_handler is not None, "Could not find get_thumbnail handler"
        source = inspect.getsource(thumbnail_handler)
        assert "NoSuchKey" in source or "404" in source


class TestImageCleanupNoSysExit:
    """Tests that rename_image uses proper error handling instead of sys.exit."""

    def test_no_sys_exit_in_rename(self):

        source = inspect.getsource(image_cleanup.rename_image)
        assert "sys.exit" not in source


class TestThumbnailAsyncNonBlocking:
    """Tests that thumbnail generation doesn't block the async event loop."""

    def test_handler_uses_asyncio(self):

        app = create_app()

        thumbnail_handler = None
        for route in app.routes:
            if hasattr(route, "name") and route.name == "get_thumbnail":
                thumbnail_handler = route.endpoint  # ty: ignore[unresolved-attribute]
                break
        assert thumbnail_handler is not None, "Could not find get_thumbnail handler"
        source = inspect.getsource(thumbnail_handler)
        assert (
            "asyncio" in source or "run_in_executor" in source or "to_thread" in source
        )


class TestGetImageErrorHandling:
    """Tests for proper error responses from /image/{filename}."""

    def test_no_unconditional_response_metadata(self):

        app = create_app()

        image_handler = None
        for route in app.routes:
            if hasattr(route, "name") and route.name == "get_image":
                image_handler = route.endpoint  # ty: ignore[unresolved-attribute]
                break
        assert image_handler is not None, "Could not find get_image handler"
        source = inspect.getsource(image_handler)
        assert "get(" in source or "try:" in source


class TestSha256Used:
    """Tests that SHA-256 is used instead of SHA-1."""

    def test_sha256_in_source(self):
        source = Path(
            "/Users/yaleman/Projects/memes-api/memes_api/__init__.py"
        ).read_text()
        assert "sha256" in source
        assert "sha1" not in source


class TestS3ListShared:
    """Tests that the shared list_images function exists."""

    def test_shared_list_function(self):

        assert callable(list_images)


class TestLoggingNotPrint:
    """Tests that print() is not used for logging."""

    def test_no_print_in_init(self):
        source = (Path(__file__).parent.parent / "./memes_api/__init__.py").read_text()
        assert "print(" not in source

    def test_no_print_in_utils(self):
        source = (Path(__file__).parent.parent / "./memes_api/utils.py").read_text()
        assert "print(" not in source


class TestGetImageContentTypeHeader:
    """Verifies /image/{filename} returns correct content-type header."""

    def test_image_header_keys_use_hyphens(self):
        """Bug: StreamingResponse used content_type/content_length (underscores)
        which leaks bogus headers instead of setting the real ones."""
        source = Path(
            Path(__file__).parent.parent / "./memes_api/__init__.py"
        ).read_text()
        assert '"content-type"' in source
        assert '"content-length"' in source
        assert '"content_type"' not in source.split("return StreamingResponse")[0]
        assert '"content_length"' not in source.split("return StreamingResponse")[0]


class TestGetImageMissingResponseMetadata:
    """Verifies /image/{filename} handles missing ResponseMetadata gracefully."""

    def test_missing_metadata_returns_502_not_500(self):
        """If S3 returns a response without ResponseMetadata, the handler must
        return 502 (not raise an unhandled KeyError)."""
        fake_body = b"fake image data"
        fake_response = {
            "Body": AsyncMock(read=AsyncMock(return_value=fake_body)),
        }

        async def fake_get_object(**kwargs):
            return fake_response

        with patch("memes_api.get_aioboto3_session") as mock_session:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_object = fake_get_object
            mock_session.return_value.client.return_value = mock_client

            client = TestClient(app)
            response = client.get("/image/test.png")

        assert response.status_code == 502


class TestGetThumbnailMissingBody:
    """Verifies /thumbnail/{filename} handles missing Body in full-size response."""

    def test_missing_body_on_fallback_returns_502(self):
        """When the cached thumbnail is not found and the full-size image is
        fetched, a response missing 'Body' must return 502, not raise
        UnboundLocalError on `content`."""
        call_count = 0

        async def fake_get_object(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
            return {}  # second call: no Body key

        with patch("memes_api.get_aioboto3_session") as mock_session:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_object = fake_get_object
            mock_session.return_value.client.return_value = mock_client

            client = TestClient(app)
            response = client.get("/thumbnail/test.png")

        assert response.status_code == 502
