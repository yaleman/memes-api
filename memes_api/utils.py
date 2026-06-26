"""utility functions"""

from json import dumps as json_dumps
import logging
from io import BytesIO
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
    heading: Optional[str]
    message: Optional[str]
    twitter_handle: Optional[str]


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
        "heading": None,
        "message": None,
        "twitter_handle": meme_config_load().twitter_handle,
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
        logging.info(json_dumps(
                {
                    "action": "s3 upload",
                    "filename": filename,
                    "result": "success",
                },
                default=str,
            ))
    except Exception as upload_error:  # pylint: disable=broad-except
        logging.error(json_dumps(
                {
                    "action": "s3 upload",
                    "filename": filename,
                    "result": "failure",
                    "error": upload_error,
                },
                default=str,
            ))
        return False
    return True
