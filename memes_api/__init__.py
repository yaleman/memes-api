""" Memes API """

from functools import lru_cache
from hashlib import sha1
from io import BytesIO
import json
import os.path
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union
import sys

from PIL import Image

import boto3

from botocore.exceptions import ClientError
from pydantic import BaseModel



from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from jinja2 import Environment, PackageLoader, select_autoescape
import jinja2.exceptions
class MemeConfig(BaseModel):
    """ config file """
    aws_access_key_id : str
    aws_secret_access_key : str
    aws_region: str
    bucket: str
    baseurl: str
    endpoint_url: Optional[str]

@lru_cache()
def meme_config_load(filepath: Optional[Path]=None) -> MemeConfig:
    """ config loader, returns a pydantic object, will try ~/.config/memes-api.json, memes-api.json, /etc/memes-api.json in order, returning the result of parsing the first one found. """
    if filepath is not None:
        if filepath.exists():
            return MemeConfig.parse_file(filepath.expanduser().resolve())
        raise FileNotFoundError(f"Couldn't find {filepath}")
    for testpath in [
        "~/.config/memes-api.json",
        "memes-api.json",
        "/etc/memes-api.json",
    ]:
        filepath = Path(testpath).expanduser().resolve()
        if filepath.exists():
            return MemeConfig.parse_file(filepath.expanduser().resolve())
    raise FileNotFoundError(f"Couldn't find {filepath}")

# pylint: disable=too-few-public-methods
class MemeBucket:
    """ handles s3 things """
    def __init__(self, meme_config: MemeConfig):
        """ init """
        self.session = boto3.Session(
            aws_access_key_id=meme_config.aws_access_key_id,
            aws_secret_access_key=meme_config.aws_secret_access_key,
            region_name=meme_config.aws_region,
        )
        if meme_config.endpoint_url is not None:

            self.s3_resource = self.session.resource(
                's3',
                endpoint_url=meme_config.endpoint_url,
                config=boto3.session.Config(signature_version='s3v4'), # type: ignore
                )
        else:
            self.s3_resource = self.session.resource(
                's3',
                )
        self.bucket = self.s3_resource.Bucket(meme_config.bucket)

    @property
    def objects(self) -> Generator[Any,None,None]:
        """ returns the objects iterator """
        iterator: Generator[Any,None,None] = self.bucket.objects.iterator()
        return iterator

# pylint: disable=too-few-public-methods
class MemeImage:
    """ gets an object """
    def __init__(self, meme_config: MemeConfig):
        """ init """
        self.bucket = meme_config.bucket
        self.session = boto3.Session(
            aws_access_key_id=meme_config.aws_access_key_id,
            aws_secret_access_key=meme_config.aws_secret_access_key,
            region_name=meme_config.aws_region,
        )
        if meme_config.endpoint_url is not None:
            self.s3_resource = self.session.resource(
                's3',
                endpoint_url=meme_config.endpoint_url,
                config=boto3.session.Config(signature_version='s3v4'), # type: ignore
                )
        else:
            self.s3_resource = self.session.resource(
                's3',
                )

    def get(self, filename: str) -> Optional[bytes]:
        """ gets an image"""
        try:
            image = self.s3_resource.Object(self.bucket, filename)
            if "Body" in image.get():
                body: bytes = image.get()["Body"]
                return body
        except ClientError as error_message:
            print(f"ClientError pulling {filename}: {error_message}", file=sys.stderr)
        return None


CSS_BASEDIR = Path(f"{os.path.dirname(__file__)}/css/").resolve().as_posix()
IMAGES_BASEDIR = Path(f"{os.path.dirname(__file__)}/images/").resolve().as_posix()
JS_BASEDIR = Path(f"{os.path.dirname(__file__)}/js/").resolve().as_posix()

THUMBNAIL_DIMENSIONS = (200,200)

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.get("/allimages")
async def all_images() -> Dict[str, List[str]]:
    """ returns all the images """
    bucket = MemeBucket(meme_config_load())
    return { "images" : [ image.key for image in bucket.objects ]}

@app.get("/thumbnail/{filename}")
async def get_thumbnail(filename: str) -> Union[HTMLResponse,StreamingResponse]:
    """ returns an image thumbnailed """

    image_class = MemeImage(meme_config_load())
    image = image_class.get(filename)

    if image is None:
        return HTMLResponse(content="", status_code=404)

    bgcolour = (255,255,255)
    tmpstorage = BytesIO()
    with Image.open(image) as tempimage:
        tempimage.thumbnail(THUMBNAIL_DIMENSIONS)
        # tempimage = tempimage.resize(THUMBNAIL_DIMENSIONS).convert('RGB')
        tempimage = tempimage.convert('RGB')
        expanded = Image.new('RGB', THUMBNAIL_DIMENSIONS, bgcolour)

        paste_x = 0
        paste_y = 0
        # work out if we need to move it within the thumbnail block
        if tempimage.height != THUMBNAIL_DIMENSIONS[0]:
            paste_y = int((THUMBNAIL_DIMENSIONS[0] - tempimage.height)/2)
        if tempimage.width != THUMBNAIL_DIMENSIONS[0]:
            paste_x = int((THUMBNAIL_DIMENSIONS[0] - tempimage.width)/2)

        expanded.paste(tempimage, (paste_x,paste_y))
        expanded.save(tmpstorage, "JPEG")
    tmpstorage.seek(0)
    imghash = sha1(tmpstorage.read())
    tmpstorage.seek(0)

    headers = {
        "ETag" : f"W/\"{imghash.hexdigest()}\"",
        "Cache-Control": "max-age=86400"
    }
    return StreamingResponse(content=tmpstorage, media_type="image/jpeg", headers=headers)

@app.get("/image_info/{filename}")
async def get_image_info(filename: str) -> HTMLResponse:
    """ gets the image info page """
    jinja2_env = Environment(
        loader=PackageLoader(package_name="memes_api", package_path="./templates"),
        autoescape=select_autoescape(),
    )
    try:
        template = jinja2_env.get_template("view_image.html")


        context: Dict[str,Any] = {
            "baseurl" : meme_config_load().baseurl,
            "image" : filename,
            "og_image" : f"{meme_config_load().baseurl}/image/{filename.replace(' ', '%20')}",
        }
        new_filecontents = template.render(**context)
        return HTMLResponse(new_filecontents)

    except jinja2.exceptions.TemplateNotFound as template_error:
        print(f"Failed to load template: {template_error}", file=sys.stderr)
    return HTMLResponse("Failed to render page, sorry!", status_code=500)

@app.get("/image/{filename}")
async def get_image(filename: str) -> Union[HTMLResponse,StreamingResponse]:
    """ returns an image """
    image_class = MemeImage(meme_config_load())
    image = image_class.get(filename)

    if image is None:
        return HTMLResponse(content="", status_code=404)
    return StreamingResponse(content=image)


@app.get("/static/js/{filename}")
async def jsfile(filename: str) -> Union[FileResponse, HTMLResponse]:
    """ return a js file """
    filepath = Path(f"{os.path.dirname(__file__)}/js/{filename}").resolve()
    if not filepath.exists() or not filepath.is_file():
        print(f"Can't find {filepath.as_posix()}")
        return HTMLResponse(status_code=404)

    if JS_BASEDIR not in filepath.as_posix():
        print(json.dumps({
            "action" : "attempt_outside_images_dir",
            "original_path" : filename,
            "resolved_path" : filepath.as_posix()
        }))
        return HTMLResponse(status_code=403)
    return FileResponse(filepath.as_posix())

@app.get("/static/css/{filename}")
async def css_get(filename: str) -> Union[FileResponse, HTMLResponse]:
    """ return the css file """
    filepath = Path(f"{os.path.dirname(__file__)}/css/{filename}").resolve()
    if not filepath.resolve().is_file() or not filepath.exists():
        return HTMLResponse(status_code=404)
    if CSS_BASEDIR not in filepath.resolve().as_posix():
        print(json.dumps({
            "action" : "attempt_outside_css_dir",
            "original_path" : filename,
            "resolved_path" : filepath.resolve()
        }, default=str))
        return HTMLResponse(status_code=403)
    return FileResponse(filepath.as_posix())

@app.get("/static/images/{filename}")
async def images_get(filename: str) -> Union[FileResponse, HTMLResponse]:
    """ return the filename file """
    filepath = Path(f"{os.path.dirname(__file__)}/images/{filename}").resolve()
    if not filepath.resolve().is_file() or not filepath.exists():
        return HTMLResponse(status_code=404)
    if IMAGES_BASEDIR not in filepath.resolve().as_posix():
        print(json.dumps({
            "action" : "attempt_outside_images_dir",
            "original_path" : filename,
            "resolved_path" : filepath.resolve()
        }, default=str))
        return HTMLResponse(status_code=403)
    return FileResponse(filepath.as_posix())


@app.get("/robots.txt")
async def robotstxt() -> HTMLResponse:
    """ robots.txt file """
    return HTMLResponse("""User-agent: *
""")

@app.get("/up")
async def healthcheck() -> HTMLResponse:
    """ healthcheck endpoint """
    return HTMLResponse("OK")

@app.get("/")
async def home_page() -> HTMLResponse: # pylint: disable=invalid-name
    """ homepage """
    jinja2_env = Environment(
        loader=PackageLoader(package_name="memes_api", package_path="./templates"),
        autoescape=select_autoescape(),
    )
    try:
        template = jinja2_env.get_template("index.html")
        context: Dict[str,Union[bool, str]] = {
            "enable_search" : True,
            "baseurl" : meme_config_load().baseurl,
        }
        new_filecontents = template.render(**context)
        return HTMLResponse(new_filecontents)

    except jinja2.exceptions.TemplateNotFound as template_error:
        print(f"Failed to load template: {template_error}", file=sys.stderr)
    return HTMLResponse("Something went wrong, sorry.", status_code=500)
