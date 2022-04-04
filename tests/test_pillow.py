""" test image things """

from email.mime import image
from pathlib import Path

from memes_api import generate_thumbnail

def test_image_thumbnail() -> None:
    """ tests generating a thumbnail """

    my_path = Path(__file__).parent.resolve()
    target_image = Path(f"{my_path}/beep-boop-i-am-a-robot.jpg")

    if not target_image.exists():
        raise FileNotFoundError("Where is the robot?")

    with target_image.open('rb') as image_handle:
        image_content = image_handle.read()

    thumbnail = generate_thumbnail(image_content)

    assert thumbnail["hash"] == "be2b9fd22aaae79a3d4decb391b18cf8645b51bd"
    assert len(thumbnail["reader"].read()) >= 4096
