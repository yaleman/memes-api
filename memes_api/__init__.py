"""Memes API"""

import json
import logging
import os.path
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aioboto3
import click
import jinja2.exceptions
import uvicorn
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import BaseModel

from .config import MemeConfig
from .constants import THUMBNAIL_BUCKET_PREFIX
from .sessions import get_aioboto3_session
from .thumbnail_cache import FailureKind, ThumbnailCache, ThumbnailFailure
from .utils import default_page_render_context

CSS_BASEDIR = Path(f"{os.path.dirname(__file__)}/css/").resolve().as_posix()
IMAGES_BASEDIR = Path(f"{os.path.dirname(__file__)}/images/").resolve().as_posix()
JS_BASEDIR = Path(f"{os.path.dirname(__file__)}/js/").resolve().as_posix()
LOGGER = logging.getLogger(__name__)


def setup_logging(level: int = logging.DEBUG) -> None:
    """sets up logging."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=level,
        handlers=[
            logging.StreamHandler(sys.stderr),
        ],
    )


meme_config = MemeConfig.default()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    cache = ThumbnailCache(meme_config)
    application.state.thumbnail_cache = cache

    async def warm() -> None:
        images = await get_allimages()
        await cache.prewarm(images.images)

    cache.start(warm())
    try:
        yield
    finally:
        await cache.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


class ImageList(BaseModel):
    """list of images from the filesystem"""

    images: list[str]


class MemeCache:
    """cache for the meme data"""

    def __init__(self, max_age: timedelta) -> None:
        self.max_age = max_age
        self.cache: ImageList | None = None
        self.timestamp: datetime | None = None

    def get(self) -> ImageList | None:
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


@app.get("/allimages")
async def get_allimages() -> ImageList:
    """returns all the images"""
    cached_response = meme_cache.get()
    if cached_response is not None:
        return cached_response

    session = aioboto3.Session(
        aws_access_key_id=meme_config.aws_access_key_id,
        aws_secret_access_key=meme_config.aws_secret_access_key,
        region_name=meme_config.aws_region,
    )

    res = None

    try:
        if meme_config.endpoint_url is not None:
            async with session.resource(
                "s3", endpoint_url=meme_config.endpoint_url
            ) as s3_resource:
                bucket = await s3_resource.Bucket(meme_config.bucket)
                res = ImageList(
                    images=[
                        image.key
                        async for image in bucket.objects.iterator()
                        if not image.key.startswith(THUMBNAIL_BUCKET_PREFIX)
                    ]
                )
        else:
            async with session.resource("s3") as s3_resource:
                bucket = await s3_resource.Bucket(meme_config.bucket)
                res = ImageList(
                    images=[
                        image.key
                        async for image in bucket.objects.iterator()
                        if not image.key.startswith(THUMBNAIL_BUCKET_PREFIX)
                    ]
                )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "NoSuchBucket":
            return ImageList(images=[])
        LOGGER.error("ClientError pulling images: %s", error)
        return ImageList(images=[])
    meme_cache.set(res)
    return res


@app.get("/thumbnail/{filename}", response_model=None)
async def get_thumbnail(filename: str) -> Response:
    """Serve local thumbnails, refreshing stale entries in the background."""
    cache: ThumbnailCache = app.state.thumbnail_cache
    result = await cache.get(filename)
    if isinstance(result, ThumbnailFailure):
        match result.kind:
            case FailureKind.MISSING:
                return HTMLResponse(f"File not found '{filename}'", status_code=404)
            case FailureKind.STORAGE | FailureKind.INVALID_IMAGE:
                return HTMLResponse("Thumbnail unavailable", status_code=503)
    return cache.response(result)


@app.get("/image_info/{filename}", response_model=None)
async def get_image_info(filename: str) -> HTMLResponse:
    """gets the image info page"""

    session = get_aioboto3_session(meme_config)

    async with session.client("s3", endpoint_url=meme_config.endpoint_url) as s3_client:
        try:
            await s3_client.get_object(Bucket=meme_config.bucket, Key=filename)
        except ClientError as error_message:
            error_code = error_message.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchKey"):
                status_code = 404
                error_text = f"File not found '{filename}'"
            else:
                LOGGER.error(
                    "error accessing bucket=%s key=%s url=/image_info/%s - %s %s",
                    meme_config.bucket,
                    filename,
                    filename,
                    error_message,
                    error_message.response,
                )
                status_code = 500
                error_text = "Something in the backend broke!"
            return HTMLResponse(error_text, status_code=status_code)

    jinja2_env = Environment(
        loader=PackageLoader(package_name="memes_api", package_path="./templates"),
        autoescape=select_autoescape(),
    )
    try:
        template = jinja2_env.get_template("view_image.html")

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
        print(f"Failed to load template: {template_error}", file=sys.stderr)
    return HTMLResponse("Failed to render page, sorry!", status_code=500)


@app.get("/image/{filename}", response_model=None)
async def get_image(filename: str) -> Response:
    """returns an image"""
    session = get_aioboto3_session(meme_config)

    async with session.client("s3", endpoint_url=meme_config.endpoint_url) as s3_client:
        try:
            image_object = await s3_client.get_object(
                Bucket=meme_config.bucket, Key=filename
            )
            ob_info = image_object["ResponseMetadata"]["HTTPHeaders"]
            if "Body" in image_object:
                content = await image_object["Body"].read()
            else:
                print("Couldn't find body!", file=sys.stderr)
                return HTMLResponse(status_code=404)
        except ClientError as error_message:
            if error_message.response.get("Error", {}).get("Code") == "NoSuchKey":
                response_status = 404
                error_text = f"File not found '{filename}'"
            else:
                response_status = 500
                error_text = f"ClientError pulling '{filename}': {error_message}"
                print(error_text, file=sys.stderr)
                if (
                    "ResponseMetadata" in error_message.response
                    and "HTTPStatusCode" in error_message.response["ResponseMetadata"]
                ):
                    response_status = error_message.response["ResponseMetadata"][
                        "HTTPStatusCode"
                    ]
            return HTMLResponse(error_text, status_code=response_status)
    headers = {
        "Cache-Control": "public, max-age=86400",
        "Content-Length": str(len(content)),
    }
    if "etag" in ob_info:
        headers["ETag"] = ob_info["etag"]
    return Response(content, media_type=ob_info["content-type"], headers=headers)


@app.get("/static/js/{filename}", response_model=None)
async def get_js_by_filename(filename: str) -> FileResponse | HTMLResponse:
    """return a js file"""
    filepath = Path(f"{os.path.dirname(__file__)}/js/{filename}").resolve()
    if not filepath.exists() or not filepath.is_file():
        LOGGER.debug(
            "Can't find %s in /static/js/%s request", filepath.as_posix(), filename
        )
        return HTMLResponse(status_code=404)

    if JS_BASEDIR not in filepath.as_posix():
        print(
            json.dumps(
                {
                    "action": "attempt_outside_images_dir",
                    "original_path": filename,
                    "resolved_path": filepath.as_posix(),
                }
            )
        )
        return HTMLResponse(status_code=403)
    return FileResponse(filepath.as_posix())


@app.get("/static/css/{filename}", response_model=None)
async def get_css_by_filename(filename: str) -> FileResponse | HTMLResponse:
    """return the css file"""
    filepath = Path(f"{os.path.dirname(__file__)}/css/{filename}").resolve()
    if not filepath.resolve().is_file() or not filepath.exists():
        return HTMLResponse(status_code=404)
    if CSS_BASEDIR not in filepath.resolve().as_posix():
        print(
            json.dumps(
                {
                    "action": "attempt_outside_css_dir",
                    "original_path": filename,
                    "resolved_path": filepath.resolve(),
                },
                default=str,
            )
        )
        return HTMLResponse(status_code=403)
    return FileResponse(filepath.as_posix())


@app.get("/static/images/{filename}", response_model=None)
async def get_static_image_by_filename(
    filename: str,
) -> FileResponse | HTMLResponse:
    """return the filename file"""
    filepath = Path(f"{os.path.dirname(__file__)}/images/{filename}").resolve()
    if not filepath.resolve().is_file() or not filepath.exists():
        return HTMLResponse(status_code=404)
    if IMAGES_BASEDIR not in filepath.resolve().as_posix():
        print(
            json.dumps(
                {
                    "action": "attempt_outside_images_dir",
                    "original_path": filename,
                    "resolved_path": filepath.resolve(),
                },
                default=str,
            )
        )
        return HTMLResponse(status_code=403)
    return FileResponse(filepath.as_posix())


@app.get("/robots.txt", response_model=None)
async def get_robotstxt() -> HTMLResponse:
    """robots.txt file"""
    return HTMLResponse(
        """User-agent: *
"""
    )


@app.get("/up", response_model=None)
async def get_healthcheck() -> HTMLResponse:
    """healthcheck endpoint"""
    return HTMLResponse("OK")


@app.get("/", response_model=None)
async def get_homepage() -> HTMLResponse:  # pylint: disable=invalid-name
    """homepage"""
    jinja2_env = Environment(
        loader=PackageLoader(package_name="memes_api", package_path="./templates"),
        autoescape=select_autoescape(),
    )
    try:
        template = jinja2_env.get_template("index.html")
        context = default_page_render_context()
        context["enable_search"] = True
        new_filecontents = template.render(**context)
        return HTMLResponse(new_filecontents)

    except jinja2.exceptions.TemplateNotFound as template_error:
        print(f"Failed to load template: {template_error}", file=sys.stderr)
    return HTMLResponse("Something went wrong, sorry.", status_code=500)


@click.command()
@click.option("--host", type=str, default="0.0.0.0")
@click.option("--port", type=int, default=8000)
@click.option("--config", help="Config path")
@click.option("--proxy-headers", is_flag=True, help="Turn on proxy headers")
@click.option("--reload", is_flag=True)
@click.option("--debug", is_flag=True)
def cli(
    host: str = "0.0.0.0",
    port: int = 8000,
    proxy_headers: bool = False,
    reload: bool = False,
    debug: bool = False,
    config: str | None = None,
) -> None:
    """server"""
    if debug:
        setup_logging(logging.DEBUG)
    else:
        setup_logging(logging.INFO)

    LOGGER.debug("proxy_headers=%s", proxy_headers)
    LOGGER.debug("reload=%s", reload)
    LOGGER.debug("debug=%s", debug)
    if config is not None:
        meme_config.load_from_file(Path(config))
    uvicorn_args = {
        "app": "memes_api:app",
        "reload": reload,
        "host": host,
        "port": port,
        "proxy_headers": proxy_headers,
    }
    if proxy_headers:
        uvicorn_args["forwarded_allow_ips"] = "*"
    uvicorn.run(**uvicorn_args)  # type: ignore
