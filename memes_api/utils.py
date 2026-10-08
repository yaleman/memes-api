"""utility functions"""

import sys
from io import BytesIO
from json import dumps as json_dumps
from typing import Any, TypedDict

from .config import MemeConfig, meme_config_load
from .constants import THUMBNAIL_BUCKET_PREFIX


class DefaultPageRenderContext(TypedDict):
    """default page context"""

    page_title: str
    page_description: str
    enable_search: bool
    baseurl: str
    og_image: str | None
    image: str | None
    image_url: str | None


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
    config: MemeConfig,
) -> bool:
    """saves the thumbnail back to s3"""
    meme_config = config
    try:
        await s3_client.upload_fileobj(
            content,
            meme_config.bucket,
            f"{THUMBNAIL_BUCKET_PREFIX}{filename}",
            ExtraArgs={
                "ContentType": "image/jpeg",
                "CacheControl": "public, max-age=86400",
            },
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
    except Exception as upload_error:  # noqa: BLE001
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
