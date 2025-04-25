"""tests the basics of the home page"""

from fastapi.testclient import TestClient

from memes_api import app

client = TestClient(app)


def test_homepage() -> None:
    """grabs the homepage"""
    for _ in range(100):
        response = client.get("/")
        assert response.status_code == 200
        assert "Memes!" in response.content.decode("utf-8")


def test_get_allimages() -> None:
    """grabs all images"""
    response = client.get("/allimages")
    assert response.status_code == 200
