"""Thumbnail encoding."""

from io import BytesIO

from PIL import Image

from .constants import THUMBNAIL_DIMENSIONS


def generate_thumbnail(content: bytes) -> bytes:
    """Generate a JPEG thumbnail."""
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
    return tmpstorage.getvalue()
