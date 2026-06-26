"""shared s3 utilities"""

from typing import List
from .constants import THUMBNAIL_BUCKET_PREFIX

async def list_images(session, config) -> List[str]:
    """list all image keys in the bucket, excluding thumbnails"""
    kwargs = {}
    if config.endpoint_url is not None:
        kwargs["endpoint_url"] = config.endpoint_url
    async with session.resource("s3", **kwargs) as s3_resource:
        bucket = await s3_resource.Bucket(config.bucket)
        return [
            image.key
            async for image in bucket.objects.iterator()
            if not image.key.startswith(THUMBNAIL_BUCKET_PREFIX)
        ]
