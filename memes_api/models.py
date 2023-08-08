""" data models """
from io import BytesIO
from typing import List
from pydantic import BaseModel, ConfigDict


class ImageList(BaseModel):
    """list of images from the filesystem"""

    images: List[str]


class ThumbnailData(BaseModel):
    """data returned from generate_thumbnail"""

    hash: str
    reader: BytesIO

    # pylint: disable=too-few-public-methods
    model_config = ConfigDict(arbitrary_types_allowed=True)
