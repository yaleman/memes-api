#!/bin/bash
# Check if there are any uncommitted changes
git diff-index --quiet HEAD -- || {
    echo "Error: There are uncommitted changes. Please commit or stash them before publishing.";
    exit 1
}

docker buildx build --platform linux/amd64,linux/arm64 --push -t "ghcr.io/yaleman/memes-api:$(git rev-parse --short HEAD)" .
docker buildx build --platform linux/amd64,linux/arm64 --push -t ghcr.io/yaleman/memes-api:latest .
docker manifest create ghcr.io/yaleman/memes-api:latest \
    "ghcr.io/yaleman/memes-api:$(git rev-parse --short HEAD)" \
    --amend ghcr.io/yaleman/memes-api:latest
docker manifest push ghcr.io/yaleman/memes-api:latest