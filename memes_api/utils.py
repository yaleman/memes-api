""" utility functions """

from json import dumps as json_dumps
from functools import lru_cache
from io import BytesIO
import sys
from typing import Any, Optional, TypedDict

from .config import meme_config_load
from .constants import THUMBNAIL_BUCKET_PREFIX


class DefaultPageRenderContext(TypedDict):
    """default page context"""

    page_title: str
    page_description: str
    enable_search: bool
    baseurl: str
    og_image: Optional[str]
    image: Optional[str]
    image_url: Optional[str]


@lru_cache()
def default_page_render_context() -> DefaultPageRenderContext:
    """returns a default context object for page rendering"""
    context: DefaultPageRenderContext = {
        "page_title": "Memes!",
        "page_description": "Sharing dem memes.",
        "enable_search": False,
        "baseurl": meme_config_load().baseurl,
        "og_image": None,
        "image": None,
        "image_url": None,
    }
    return context


async def save_thumbnail(
    s3_client: Any,
    filename: str,
    content: BytesIO,
) -> bool:
    """saves the thumbnail back to s3"""
    meme_config = meme_config_load()
    try:
        await s3_client.upload_fileobj(
            content,
            meme_config.bucket,
            f"{THUMBNAIL_BUCKET_PREFIX}{filename}",
        )
        print(
            json_dumps(
                {
                    "action": "s3 upload",
                    "filename": filename,
                    "result": "success",
                },
                default=str,
            ),
            file=sys.stderr,
        )
    except Exception as upload_error:  # pylint: disable=broad-except
        print(
            json_dumps(
                {
                    "action": "s3 upload",
                    "filename": filename,
                    "result": "failure",
                    "error": upload_error,
                },
                default=str,
            ),
            file=sys.stderr,
        )
        return False
    return True
