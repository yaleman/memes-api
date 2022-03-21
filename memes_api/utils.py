""" utility functions """

from functools import lru_cache
from io import BytesIO
import sys
from typing import Any, Optional, TypedDict

from .config import meme_config_load
from .constants import THUMBNAIL_BUCKET_PREFIX

class DefaultContext(TypedDict):
    """ default page context """
    page_title: str
    page_description: str
    enable_search: bool
    baseurl: str
    og_image: Optional[str]
    image: Optional[str]
    image_url: Optional[str]

@lru_cache()
def default_context() -> DefaultContext:
    """ returns a default context object """
    context: DefaultContext = {
        "page_title" : "Memes!",
        "page_description" : "Sharing dem memes.",
        "enable_search" : False,
        "baseurl" : meme_config_load().baseurl,
        "og_image" : None,
        "image" : None,
        "image_url" : None,
    }
    return context

async def save_thumbnail(
    s3_client: Any,
    filename: str,
    content: BytesIO,
    ) -> bool:
    """ saves the thumbnail back to s3 """
    meme_config = meme_config_load()
    try:
        await s3_client.upload_fileobj(
            content,
            meme_config.bucket,
            f"{THUMBNAIL_BUCKET_PREFIX}{filename}",
            )
        print(f"s3 upload {filename=} successful")
    except Exception as upload_error: #pylint: disable=broad-except
        print(f"Failed to upload thumbnail {filename=} {upload_error=}", file=sys.stderr)
        return False
    return True
