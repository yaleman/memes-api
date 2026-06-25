"""constant values"""

from enum import IntEnum

THUMBNAIL_BUCKET_PREFIX = "thumbs/"


class ThumbnailDimensions(IntEnum):
    X = 200
    Y = 200

    @classmethod
    def size(cls) -> tuple[int, int]:
        return (cls.X, cls.Y)
