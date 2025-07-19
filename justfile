default: checks

checks: lint types test

coverage:
    uv run coverage run -m pytest
    uv run coveralls


test:
    uv run pytest

lint:
    uv run ruff check memes_api tests

types:
    uv run mypy --strict memes_api tests
    uv run ty check

docker_build:
    docker buildx build \
        --load \
        -t ghcr.io/yaleman/memes-api:$(git rev-parse --short HEAD) \
        -t ghcr.io/yaleman/memes-api:latest \
        .

docker_run:
    docker compose up --build

# Publish the Docker image to GitHub Container Registry, won't run if there's uncommitted changes
docker_publish:
    #!/bin/bash
    # Check if there are any uncommitted changes
    git diff-index --quiet HEAD -- || {
        echo "Error: There are uncommitted changes. Please commit or stash them before publishing.";
        exit 1
    }

    docker buildx build --platform linux/amd64,linux/arm64 --push -t ghcr.io/yaleman/memes-api:$(git rev-parse --short HEAD) .
    docker buildx build --platform linux/amd64,linux/arm64 --push -t ghcr.io/yaleman/memes-api:latest .
    docker manifest create ghcr.io/yaleman/memes-api:latest \
        ghcr.io/yaleman/memes-api:$(git rev-parse --short HEAD) \
        --amend ghcr.io/yaleman/memes-api:latest
    docker manifest push ghcr.io/yaleman/memes-api:latest