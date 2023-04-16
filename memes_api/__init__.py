""" Memes API """

from hashlib import sha1

from io import BytesIO
import json
import os.path
from pathlib import Path
import random
import string
from typing import Callable, List, Optional, Tuple, Union
import sys
from authlib.integrations.starlette_client import OAuth, OAuthError
from authlib.oauth2 import TokenAuth, ClientAuth

from loguru import logger

import aioboto3  # type: ignore
from botocore.exceptions import ClientError
import click
from fastapi import Request, Depends, FastAPI, HTTPException, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from starlette.responses import RedirectResponse
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware


from jinja2 import Environment, PackageLoader, select_autoescape
import jinja2.exceptions
from PIL import Image
from pydantic import BaseModel
import uvicorn

from .sessions import get_aioboto3_session
from .config import meme_config_load
from .constants import THUMBNAIL_BUCKET_PREFIX, THUMBNAIL_DIMENSIONS
from .models import ImageList, ThumbnailData
from .utils import default_page_render_context, save_thumbnail

# TODO: store a randomized secret in a file
SESSION_SECRET = 'REPLACE WITH A PROPER SECRET OF YOUR CHOICE'

CSS_BASEDIR = Path(f"{os.path.dirname(__file__)}/css/").resolve().as_posix()
IMAGES_BASEDIR = Path(f"{os.path.dirname(__file__)}/images/").resolve().as_posix()
JS_BASEDIR = Path(f"{os.path.dirname(__file__)}/js/").resolve().as_posix()

app = FastAPI()
# app.add_middleware(GZipMiddleware, minimum_size=1000)

# add session middleware (this is used internally by starlette to execute the authorization flow)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET,
                   max_age=60 * 60 * 24 * 7)  # one week, in seconds


starlette_config = Config(environ={})  # you could also read the client ID and secret from a .env file
oauth = OAuth(starlette_config)
if meme_config_load().oidc_client_id is not None:
    memeconfig = meme_config_load()
    if memeconfig.oidc_secret is None:
        raise ValueError("Please configure a secret for OIDC")
    if memeconfig.oidc_discovery_url is None:
        raise ValueError("Please configure a discovery URL for OIDC")

    client_kwargs = {
        'scope': memeconfig.oidc_scope,
    }
    if memeconfig.oidc_use_pkce:
        client_kwargs["code_challenge_method"] = "S256" # use PKCE

    oauth.register(  # this allows us to call oauth.discord later on
        'oauth2',
        scope=memeconfig.oidc_scope,
        client_id=memeconfig.oidc_client_id,
        client_secret=memeconfig.oidc_secret,
        server_metadata_url=memeconfig.oidc_discovery_url,
        client_kwargs=client_kwargs
    )


# define the endpoints for the OAuth2 flow
@app.get('/login')
async def login(request: Request):
    """OAuth2 flow, step 1: have the user log into Discord to obtain an authorization code grant
    """
    return await oauth.oauth2.authorize_redirect(request, str(request.url_for('auth')))

@app.get('/logout')
async def logout(request: Request):
    """ nuke the login session    """
    if "token" in request.session:
        request.session.pop("token")
    request.session.clear()
    return RedirectResponse(url='/')

@app.get('/auth')
@logger.catch
async def auth(request: Request):
    """OAuth2 flow, step 2: exchange the authorization code for access token
    """

    # exchange auth code for token
    try:
        print(f"request {dir(request)}", file=sys.stderr)

        token = await oauth.oauth2.authorize_access_token(request)
        print(token.get("userinfo"), file=sys.stderr)
    except OAuthError as error:
        return HTMLResponse(f'<h3>{error.error}</h3><a href="/">Back</a>')

    # you now have an auth token. Do whatever you need with it
    request.session.update({"token": token })
    return RedirectResponse(url='/')

@app.get("/admin")
async def get_admin(request: Request):
    """ admin page, protected by admin"""
    token = request.session.get("token")
    if token is None:
        return RedirectResponse(url=request.url_for('login'))
    if token:
        print(f"Token! {token}", file=sys.stderr)
        jinja2_env = Environment(
            loader=PackageLoader(package_name="memes_api", package_path="./templates"),
            autoescape=select_autoescape(),
        )
        try:
            template = jinja2_env.get_template("admin.html")
            context = default_page_render_context()
            new_filecontents = template.render(**context)
            return HTMLResponse(new_filecontents)

        except jinja2.exceptions.TemplateNotFound as template_error:
            print(f"Failed to load template: {template_error}", file=sys.stderr)
        return HTMLResponse("Something went wrong, sorry.", status_code=500)

@app.get("/allimages")
async def get_allimages() -> ImageList:
    """returns all the images"""
    meme_config = meme_config_load()
    session = aioboto3.Session(
        aws_access_key_id=meme_config.aws_access_key_id,
        aws_secret_access_key=meme_config.aws_secret_access_key,
        region_name=meme_config.aws_region,
    )

    if meme_config.endpoint_url is not None:
        async with session.resource(
            "s3", endpoint_url=meme_config.endpoint_url
        ) as s3_resource:
            bucket = await s3_resource.Bucket(meme_config.bucket)
            return ImageList(images=[
                    image.key
                    async for image in bucket.objects.iterator()
                    if not image.key.startswith(THUMBNAIL_BUCKET_PREFIX)
                ]
            )
    else:
        async with session.resource("s3") as s3_resource:
            bucket = await s3_resource.Bucket(meme_config.bucket)
            return ImageList(images=[
                    image.key
                    async for image in bucket.objects.iterator()
                    if not image.key.startswith(THUMBNAIL_BUCKET_PREFIX)
                ]
            )



def generate_thumbnail(content: bytes) -> ThumbnailData:
    """generate a thumbnail and return a BytesIO object to read it back"""
    tmpstorage = BytesIO()
    with Image.open(BytesIO(content)) as tempimage:
        tempimage.thumbnail(THUMBNAIL_DIMENSIONS)
        tempimage = tempimage.convert("RGB")
        expanded = Image.new("RGB", THUMBNAIL_DIMENSIONS, (255, 255, 255))

        paste_x = 0
        paste_y = 0
        # work out if we need to move it within the thumbnail block
        if tempimage.height != THUMBNAIL_DIMENSIONS[0]:
            paste_y = int((THUMBNAIL_DIMENSIONS[0] - tempimage.height) / 2)
        if tempimage.width != THUMBNAIL_DIMENSIONS[0]:
            paste_x = int((THUMBNAIL_DIMENSIONS[0] - tempimage.width) / 2)

        expanded.paste(tempimage, (paste_x, paste_y))
        expanded.save(tmpstorage, "JPEG")
    tmpstorage.seek(0)
    imghash = sha1(tmpstorage.read()).hexdigest()
    tmpstorage.seek(0)
    return ThumbnailData(hash=imghash, reader=tmpstorage)


@app.get("/thumbnail/{filename}", response_model=None)
async def get_thumbnail(filename: str) -> Union[HTMLResponse, StreamingResponse]:
    """returns an image thumbnailed

    first it tries to pull a pre-cached thumbnail and just returns that

    if not, it'll pull the original image and make a thumb from that
    """
    async with get_aioboto3_session().client(
        "s3",
        endpoint_url=meme_config_load().endpoint_url,
    ) as s3_client:

        # try and get the pre-cached thumbnail
        try:
            image_object = await s3_client.get_object(
                Bucket=meme_config_load().bucket,
                Key=f"{THUMBNAIL_BUCKET_PREFIX}{filename}",
            )
            if "Body" in image_object:
                content = await image_object["Body"].read()
                return StreamingResponse(BytesIO(content))
        except ClientError:
            # thumbnail wasn't found, or wasn't loadable
            pass

        try:
            image_object = await s3_client.get_object(
                Bucket=meme_config_load().bucket, Key=filename
            )
            if "Body" in image_object:
                content = await image_object["Body"].read()
            else:
                return HTMLResponse(status_code=404)
        except ClientError as error_message:
            if error_message.response['Error']['Code'] == "NoSuchKey":
                response_status = 404
                error_text=f"File not found '{filename}'"
            else:
                error_text = f"ClientError pulling '{filename}': {error_message}"
                print(error_text, file=sys.stderr)
                response_status = 500
                if "ResponseMetadata" in error_message.response:
                    if "HTTPStatusCode" in error_message.response["ResponseMetadata"]:
                        response_status = error_message.response["ResponseMetadata"][
                            "HTTPStatusCode"
                        ]
            return HTMLResponse(error_text, status_code=response_status)
    thumbnail_data = generate_thumbnail(content)

    # save the thunbnail to s3
    async with get_aioboto3_session().client(
        "s3",
        endpoint_url=meme_config_load().endpoint_url,
    ) as s3_client:
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
    jinja2_env = Environment(
        loader=PackageLoader(package_name="memes_api", package_path="./templates"),
        autoescape=select_autoescape(),
    )
    try:
        template = jinja2_env.get_template("view_image.html")

        context = default_page_render_context()
        context["image"] = filename
        context[
            "og_image"
        ] = f"{context['baseurl']}/thumbnail/{filename.replace(' ', '%20')}"
        context[
            "image_url"
        ] = f"{context['baseurl']}/image/{filename.replace(' ', '%20')}"
        context["page_title"] = f"Memes! - {filename}"
        new_filecontents = template.render(**context)
        return HTMLResponse(new_filecontents)

    except jinja2.exceptions.TemplateNotFound as template_error:
        print(f"Failed to load template: {template_error}", file=sys.stderr)
    return HTMLResponse("Failed to render page, sorry!", status_code=500)


@app.get("/image/{filename}", response_model=None)
async def get_image(filename: str) -> Union[HTMLResponse, StreamingResponse]:
    """returns an image"""
    meme_config = meme_config_load()
    session = get_aioboto3_session()

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
            if error_message.response['Error']['Code'] == "NoSuchKey":
                response_status = 404
                error_text=f"File not found '{filename}'"
            else:
                response_status = 500
                error_text = f"ClientError pulling '{filename}': {error_message}"
                print(error_text, file=sys.stderr)
                if "ResponseMetadata" in error_message.response:
                    if "HTTPStatusCode" in error_message.response["ResponseMetadata"]:
                        response_status = error_message.response["ResponseMetadata"][
                            "HTTPStatusCode"
                        ]
            return HTMLResponse(error_text, status_code=response_status)
    headers = {
        "content_type": ob_info["content-type"],
        "content_length": ob_info["content-length"],
    }
    return StreamingResponse(BytesIO(content), headers=headers)


@app.get("/static/js/{filename}", response_model=None)
async def get_js_by_filename(filename: str) -> Union[FileResponse, HTMLResponse]:
    """return a js file"""
    filepath = Path(f"{os.path.dirname(__file__)}/js/{filename}").resolve()
    if not filepath.exists() or not filepath.is_file():
        print(f"Can't find {filepath.as_posix()}")
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
async def get_css_by_filename(filename: str) -> Union[FileResponse, HTMLResponse]:
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
) -> Union[FileResponse, HTMLResponse]:
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
async def get_homepage(request: Request) -> HTMLResponse:  # pylint: disable=invalid-name
    """homepage"""
    jinja2_env = Environment(
        loader=PackageLoader(package_name="memes_api", package_path="./templates"),
        autoescape=select_autoescape(),
    )
    try:
        template = jinja2_env.get_template("index.html")
        context = default_page_render_context()
        if request.session.get('token'):
            context["logged_in"] = True

        new_filecontents = template.render(**context)
        return HTMLResponse(new_filecontents)

    except jinja2.exceptions.TemplateNotFound as template_error:
        print(f"Failed to load template: {template_error}", file=sys.stderr)
    return HTMLResponse("Something went wrong, sorry.", status_code=500)


@click.command()
@click.option("--host", type=str, default="0.0.0.0")
@click.option("--ssl-keyfile", type=str)
@click.option("--ssl-certfile", type=str)
@click.option("--port", type=int, default=8000)
@click.option("--proxy-headers", is_flag=True, help="Turn on proxy headers")
@click.option("--reload", is_flag=True)
def cli(
    host: str = "0.0.0.0",
    port: int = 8000,
    proxy_headers: bool = False,
    reload: bool = False,
    ssl_keyfile: Optional[str] = None,
    ssl_certfile: Optional[str] = None,
) -> None:
    """server"""
    print(f"{proxy_headers=}", file=sys.stderr)
    print(f"{reload=}", file=sys.stderr)
    uvicorn_args = {
        "app": "memes_api:app",
        "reload": reload,
        "host": host,
        "port": port,
        "proxy_headers": proxy_headers,
    }
    if ssl_keyfile is not None:
        uvicorn_args["ssl_keyfile"] = ssl_keyfile
    if ssl_certfile is not None:
        uvicorn_args["ssl_certfile"] = ssl_certfile
    if proxy_headers:
        uvicorn_args["forwarded_allow_ips"] = "*"
    uvicorn.run(**uvicorn_args) #type: ignore
