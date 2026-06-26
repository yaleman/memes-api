""" test image things """

from io import BytesIO
from pathlib import Path

from PIL import Image

from memes_api import generate_thumbnail


def test_image_thumbnail() -> None:
    """tests generating a thumbnail"""

    my_path = Path(__file__).parent.resolve()
    target_image = Path(f"{my_path}/beep-boop-i-am-a-robot.jpg")

    if not target_image.exists():
        raise FileNotFoundError("Where is the robot?")

    with target_image.open("rb") as image_handle:
        image_content = image_handle.read()

    thumbnail = generate_thumbnail(image_content)

    assert len(thumbnail.reader.read()) >= 4096


def test_thumbnail_from_palette_mode_png() -> None:
    """generate_thumbnail must not corrupt palette-mode images.

    Previously the code used Image.frombytes(mode, size, img.tobytes())
    which can lose palette / transparency info for "P" mode images.
    Using img.copy() preserves the palette correctly.
    """
    img = Image.new("P", (400, 300), color=0)
    img.putpalette([i % 256 for i in range(768)])

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    thumbnail = generate_thumbnail(buf.read())
    result = thumbnail.reader.read()

    assert len(result) > 0

    with Image.open(BytesIO(result)) as verify:
        assert verify.mode == "RGB"
        assert verify.size == (200, 200)


def test_thumbnail_from_rgba_mode() -> None:
    """RGBA images (e.g. transparent PNGs) should thumbnail without corruption."""
    img = Image.new("RGBA", (500, 400), color=(255, 0, 0, 128))

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    thumbnail = generate_thumbnail(buf.read())
    result = thumbnail.reader.read()

    assert len(result) > 0

    with Image.open(BytesIO(result)) as verify:
        assert verify.mode == "RGB"
        assert verify.size == (200, 200)
