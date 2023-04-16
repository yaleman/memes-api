""" data models """
from io import BytesIO
from typing import List
from pydantic import BaseModel

class ImageList(BaseModel):
    """ list of images from the filesystem """
    images: List[str]

class ThumbnailData(BaseModel):
    """data returned from generate_thumbnail"""
    hash: str
    reader: BytesIO

    # pylint: disable=too-few-public-methods
    class Config:
        """ config sub-class"""
        arbitrary_types_allowed = True
