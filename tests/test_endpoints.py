"""tests the basics of the home page"""

import random
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


def test_thumbnail() -> None:
    response = client.get("/thumbnail/12345")
    assert response.status_code == 404


def test_openapi() -> None:
    openapi = app.openapi()
    for key, value in openapi.get("paths", {}).items():
        # print(f"{key}: {value}")
        if "{" not in key:
            if value.get("get"):
                print(f"Testing GET {key}")
                res = client.get(key)
                assert res.status_code == 200
                # assert value.get("get").get("summary") is not None
        else:
            if value.get("get"):
                # print(json.dumps(value, indent=4))
                needed_keys = {}
                for param in value.get("get").get("parameters"):
                    if param.get("name") not in needed_keys:
                        needed_keys[param.get("name")] = (
                            f"asfsafasdf{random.randint(1000, 99999999)}"
                        )
                print(f"Testing GET {key} with a random input")
                res = client.get(key.format(**needed_keys))
                if res.status_code != 404:
                    print(f"Response: {res.content.decode('utf-8')}")
                assert res.status_code == 404
