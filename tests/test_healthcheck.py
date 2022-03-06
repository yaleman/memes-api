""" tests that the healthcheck works """

from fastapi.testclient import TestClient

from memes_api import app

client = TestClient(app)


def test_healthcheck():
    """tests the healthcheck works"""
    response = client.get("/up")
    assert response.status_code == 200
    assert response.content == b"OK"
