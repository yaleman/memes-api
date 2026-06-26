"""Memes API"""

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from io import BytesIO
import logging
import os.path
from pathlib import Path
from typing import List, Optional, Union
import sys

from botocore.exceptions import ClientError
import click
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    StreamingResponse,
    PlainTextResponse,
)

from jinja2 import Environment, PackageLoader, select_autoescape
import jinja2.exceptions
from PIL import Image
from pydantic import BaseModel, ConfigDict
import uvicorn

from .sessions import get_aioboto3_session
from .config import MemeConfig
from .constants import THUMBNAIL_BUCKET_PREFIX, ThumbnailDimensions
from .s3_utils import list_images
from .utils import default_page_render_context, save_thumbnail


CSS_BASEDIR = Path(f"{os.path.dirname(__file__)}/css/").resolve().as_posix()
IMAGES_BASEDIR = Path(f"{os.path.dirname(__file__)}/images/").resolve().as_posix()
JS_BASEDIR = Path(f"{os.path.dirname(__file__)}/js/").resolve().as_posix()


def setup_logging(level: int = logging.DEBUG) -> None:
    """sets up logging."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=level,
        handlers=[
            logging.StreamHandler(sys.stderr),
        ],
    )


JINJA2_ENV = Environment(
    loader=PackageLoader(package_name="memes_api", package_path="./templates"),
    autoescape=select_autoescape(),
)


def _error_response(status_code: int, heading: str, message: str) -> HTMLResponse:
    """render a simple error page"""
    template = JINJA2_ENV.get_template("error.html")
    context = default_page_render_context()
    context["page_title"] = f"Error {status_code}"
    context["heading"] = heading
    context["message"] = message
    return HTMLResponse(template.render(**context), status_code=status_code)


class ImageList(BaseModel):
    """list of images from the filesystem, with optional error return"""

    images: List[str]
    error: Optional[str] = None


class ThumbnailData(BaseModel):
    """data returned from generate_thumbnail"""

    hash: str
    reader: BytesIO

    model_config = ConfigDict(arbitrary_types_allowed=True)


class MemeCache:
    """cache for the meme data"""

    def __init__(self, max_age: timedelta) -> None:
        self.max_age = max_age
        self.cache: Optional[ImageList] = None
        self.timestamp: Optional[datetime] = None

    def get(self) -> Optional[ImageList]:
        """get the cache, or None if it's stale or not set"""
        if self.timestamp is None:
            return None
        if self.timestamp + self.max_age < datetime.now(UTC):
            self.cache = None
            self.timestamp = None

        return self.cache

    def clear(self) -> None:
        """clear the cache"""
        self.cache = None
        self.timestamp = None

    def set(self, value: ImageList) -> None:
        """set the cache"""
        self.cache = value
        self.timestamp = datetime.now(UTC)


meme_cache = MemeCache(max_age=timedelta(minutes=15))


def generate_thumbnail(content: bytes) -> ThumbnailData:
    """generate a thumbnail and return a BytesIO object to read it back"""
    tmpstorage = BytesIO()
    with Image.open(BytesIO(content)) as tempimage:
        tempdata = tempimage.copy()
    tempdata.thumbnail(ThumbnailDimensions.size(), Image.Resampling.LANCZOS)
    tempdata = tempdata.convert("RGB")
    expanded = Image.new("RGB", ThumbnailDimensions.size(), (255, 255, 255))

    paste_x = 0
    paste_y = 0
    if tempdata.height != ThumbnailDimensions.Y:
        paste_y = int((ThumbnailDimensions.Y - tempdata.height) / 2)
    if tempdata.width != ThumbnailDimensions.X:
        paste_x = int((ThumbnailDimensions.X - tempdata.width) / 2)

    expanded.paste(tempdata, (paste_x, paste_y))
    expanded.save(tmpstorage, "JPEG")
    tmpstorage.seek(0)
    imghash = sha256(tmpstorage.read()).hexdigest()
    tmpstorage.seek(0)
    return ThumbnailData(hash=imghash, reader=tmpstorage)


def create_app(config: Optional[MemeConfig] = None) -> FastAPI:
    """Create a FastAPI application with the given configuration.

    If no config is provided, loads from default locations.
    """
    app_config = config if config is not None else MemeConfig.default()

    new_app = FastAPI()
    new_app.add_middleware(GZipMiddleware, minimum_size=1000)
    new_app.state.config = app_config

    _register_routes(new_app)

    return new_app


def _register_routes(app: FastAPI) -> None:
    """Register all route handlers on the given app instance."""

    @app.get("/allimages")
    async def get_allimages() -> ImageList:
        """returns all the images"""
        cached_response = meme_cache.get()
        if cached_response is not None:
            return cached_response

        session = get_aioboto3_session(app.state.config)

        res: ImageList

        try:
            images = await list_images(session, app.state.config)
            res = ImageList(images=images)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "NoSuchBucket":
                return ImageList(images=[], error="Bucket not found")
            logging.error("ClientError pulling images: %s", error)
            return ImageList(images=[], error="Error pulling images")
        meme_cache.set(res)
        return res

    @app.get("/thumbnail/{filename}", response_model=None)
    async def get_thumbnail(filename: str) -> Union[HTMLResponse, StreamingResponse]:
        """returns an image thumbnailed

        first it tries to pull a pre-cached thumbnail and just returns that

        if not, it'll pull the original image and make a thumb from that
        """
        session = get_aioboto3_session(app.state.config)
        async with session.client(
            "s3",
            endpoint_url=app.state.config.endpoint_url,
        ) as s3_client:
            try:
                image_object = await s3_client.get_object(
                    Bucket=app.state.config.bucket,
                    Key=f"{THUMBNAIL_BUCKET_PREFIX}{filename}",
                )
                if "Body" in image_object:
                    content = await image_object["Body"].read()
                    return StreamingResponse(BytesIO(content))
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey"):
                    logging.error(
                        "Error checking cached thumbnail '%s': %s", filename, e
                    )
                    raise

            try:
                image_object = await s3_client.get_object(
                    Bucket=app.state.config.bucket, Key=filename
                )
                if "Body" not in image_object:
                    logging.error("No body in response for '%s'", filename)
                    return _error_response(
                        502, "Image unavailable", "The image could not be retrieved."
                    )
                content = await image_object["Body"].read()  # type: ignore[possibly-undefined]
            except ClientError as error_message:
                error_code = error_message.response.get("Error", {}).get("Code")
                if error_code in ["404", "NoSuchKey"]:
                    return _error_response(
                        404, "File not found", f"The image '{filename}' doesn't exist."
                    )
                logging.error(
                    "ClientError pulling image for thumbnail '%s': %s",
                    filename,
                    error_message,
                )
                response_status = 500
                if "ResponseMetadata" in error_message.response:
                    if "HTTPStatusCode" in error_message.response["ResponseMetadata"]:
                        response_status = error_message.response["ResponseMetadata"][
                            "HTTPStatusCode"
                        ]
                return _error_response(
                    response_status,
                    "Server error",
                    "Something went wrong retrieving the image.",
                )

            thumbnail_data = await asyncio.to_thread(generate_thumbnail, content)

            await save_thumbnail(s3_client, filename, thumbnail_data.reader)
        thumbnail_data.reader.seek(0)

        imghash = thumbnail_data.hash
        headers = {
            "ETag": f'W/"{imghash}"',
            "Cache-Control": "max-age=86400",
        }
        return StreamingResponse(
            content=thumbnail_data.reader, media_type="image/jpeg", headers=headers
        )

    @app.get("/image_info/{filename}", response_model=None)
    async def get_image_info(filename: str) -> HTMLResponse:
        """gets the image info page"""
        session = get_aioboto3_session(app.state.config)

        async with session.client(
            "s3", endpoint_url=app.state.config.endpoint_url
        ) as s3_client:
            try:
                await s3_client.get_object(Bucket=app.state.config.bucket, Key=filename)
            except ClientError as error_message:
                error_code = error_message.response.get("Error", {}).get("Code")
                if error_code in ("404", "NoSuchKey"):
                    return _error_response(
                        404, "File not found", f"The image '{filename}' doesn't exist."
                    )
                logging.error(
                    "error accessing bucket=%s key=%s url=/image_info/%s - %s %s",
                    app.state.config.bucket,
                    filename,
                    filename,
                    error_message,
                    error_message.response,
                )
                return _error_response(
                    500, "Server error", "Something went wrong retrieving the image."
                )

        try:
            template = JINJA2_ENV.get_template("view_image.html")

            context = default_page_render_context()
            context["image"] = filename
            context["og_image"] = (
                f"{context['baseurl']}/thumbnail/{filename.replace(' ', '%20')}"
            )
            context["image_url"] = (
                f"{context['baseurl']}/image/{filename.replace(' ', '%20')}"
            )
            context["page_title"] = f"Memes! - {filename}"
            new_filecontents = template.render(**context)
            return HTMLResponse(new_filecontents)

        except jinja2.exceptions.TemplateNotFound as template_error:
            logging.error(f"Failed to load template: {template_error}")
        return HTMLResponse("Failed to render page, sorry!", status_code=500)

    @app.get("/image/{filename}", response_model=None)
    async def get_image(filename: str) -> Union[HTMLResponse, StreamingResponse]:
        """returns an image"""
        session = get_aioboto3_session(app.state.config)

        async with session.client(
            "s3", endpoint_url=app.state.config.endpoint_url
        ) as s3_client:
            try:
                image_object = await s3_client.get_object(
                    Bucket=app.state.config.bucket, Key=filename
                )
                try:
                    ob_info = image_object["ResponseMetadata"]["HTTPHeaders"]
                except (KeyError, TypeError):
                    logging.error(
                        "Unexpected S3 response structure for '%s': %s",
                        filename,
                        image_object,
                    )
                    return _error_response(
                        502, "Server error", "Unexpected storage response."
                    )
                if "Body" not in image_object:
                    logging.warning("Couldn't find body for '%s'", filename)
                    return _error_response(
                        502, "Server error", "The image could not be retrieved."
                    )
                content = await image_object["Body"].read()
            except ClientError as error_message:
                if error_message.response.get("Error", {}).get("Code") == "NoSuchKey":
                    return _error_response(
                        404, "File not found", f"The image '{filename}' doesn't exist."
                    )
                logging.error("ClientError pulling '%s': %s", filename, error_message)
                response_status = 500
                if "ResponseMetadata" in error_message.response:
                    if "HTTPStatusCode" in error_message.response["ResponseMetadata"]:
                        response_status = error_message.response["ResponseMetadata"][
                            "HTTPStatusCode"
                        ]
                return _error_response(
                    response_status,
                    "Server error",
                    "Something went wrong retrieving the image.",
                )
        headers = {
            "content-type": str(
                ob_info.get("content-type", "application/octet-stream")
            ),
            "content-length": str(ob_info.get("content-length", len(content))),
        }
        return StreamingResponse(BytesIO(content), headers=headers)

    @app.get("/static/js/{filename}", response_model=None)
    async def get_js_by_filename(filename: str) -> Union[FileResponse, HTMLResponse]:
        """return a js file"""
        filepath = Path(f"{os.path.dirname(__file__)}/js/{filename}").resolve()
        base_dir = Path(JS_BASEDIR).resolve()
        if not filepath.is_relative_to(base_dir):
            logging.warning(
                "attempt_outside_js_dir original_path=%s resolved_path=%s",
                filename,
                filepath.as_posix(),
            )
            return HTMLResponse(status_code=403)
        if not filepath.is_file():
            logging.debug(
                "Can't find %s in /static/js/%s request", filepath.as_posix(), filename
            )
            return HTMLResponse(status_code=404)
        return FileResponse(filepath.as_posix())

    @app.get("/static/css/{filename}", response_model=None)
    async def get_css_by_filename(filename: str) -> Union[FileResponse, HTMLResponse]:
        """return the css file"""
        filepath = Path(f"{os.path.dirname(__file__)}/css/{filename}").resolve()
        base_dir = Path(CSS_BASEDIR).resolve()
        if not filepath.is_relative_to(base_dir):
            logging.warning(
                "attempt_outside_css_dir original_path=%s resolved_path=%s",
                filename,
                filepath.as_posix(),
            )
            return HTMLResponse(status_code=403)
        if not filepath.is_file():
            return HTMLResponse(status_code=404)
        return FileResponse(filepath.as_posix())

    @app.get("/static/images/{filename}", response_model=None)
    async def get_static_image_by_filename(
        filename: str,
    ) -> Union[FileResponse, HTMLResponse]:
        """return the filename file"""
        filepath = Path(f"{os.path.dirname(__file__)}/images/{filename}").resolve()
        base_dir = Path(IMAGES_BASEDIR).resolve()
        if not filepath.is_relative_to(base_dir):
            logging.warning(
                "attempt_outside_images_dir original_path=%s resolved_path=%s",
                filename,
                filepath.as_posix(),
            )
            return HTMLResponse(status_code=403)
        if not filepath.is_file():
            return HTMLResponse(status_code=404)
        return FileResponse(filepath.as_posix())

    @app.get("/robots.txt", response_model=None)
    async def get_robotstxt() -> HTMLResponse:
        """robots.txt file"""
        return HTMLResponse(
            """User-agent: *
"""
        )

    @app.get("/up", response_model=None)
    async def get_healthcheck() -> PlainTextResponse:
        """healthcheck endpoint"""
        return PlainTextResponse("OK")

    @app.get("/", response_model=None)
    async def get_homepage() -> HTMLResponse:
        """homepage"""
        try:
            template = JINJA2_ENV.get_template("index.html")
            context = default_page_render_context()
            context["enable_search"] = True
            new_filecontents = template.render(**context)
            return HTMLResponse(new_filecontents)

        except jinja2.exceptions.TemplateNotFound as template_error:
            logging.error(f"Failed to load template: {template_error}")
        return HTMLResponse("Something went wrong, sorry.", status_code=500)


@click.command()
@click.option("--host", type=str, default="0.0.0.0")
@click.option("--port", type=int, default=8000)
@click.option("--proxy-headers", is_flag=True, help="Turn on proxy headers")
@click.option("--reload", is_flag=True)
@click.option("--debug", is_flag=True)
def cli(
    host: str = "0.0.0.0",
    port: int = 8000,
    proxy_headers: bool = False,
    reload: bool = False,
    debug: bool = False,
) -> None:
    """server"""
    if debug:
        setup_logging(logging.DEBUG)
    else:
        setup_logging(logging.INFO)

    logging.debug("proxy_headers=%s", proxy_headers)
    logging.debug("reload=%s", reload)
    logging.debug("debug=%s", debug)

    uvicorn_args = {
        "reload": reload,
        "host": host,
        "port": port,
        "proxy_headers": proxy_headers,
    }
    if proxy_headers:
        uvicorn_args["forwarded_allow_ips"] = "*"
    uvicorn.run(app="memes_api:create_app", factory=True, **uvicorn_args)  # ty: ignore[invalid-argument-type]
