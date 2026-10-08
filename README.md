# memes-api

A memes API thing

## Installation

Install this library using `pip`:

    python -m pip install git+https://github.com/yaleman/memes-api

## Usage

python -m memes_api

## Development

To contribute to this library, first checkout the code. Then create a new virtual environment:

    cd memes-api
    uv venv

## Thumbnail caching

Thumbnails are cached locally in `~/.cache/memes-api/thumbnails`. Set
`thumbnail_cache_dir` in the JSON configuration to override the directory. Docker
Compose mounts the `thumbnail_cache` named volume there; its contents survive
container replacement. The image creates the directory with ownership for the
application user. If you customize the location, provide a writable mount there.

Entries are fresh for 24 hours. Expired thumbnails are served immediately while
refreshing from S3. A confirmed missing object removes the local entry; transient
storage failures retain it. Startup prewarms the collection in the background,
with at most four simultaneous thumbnail storage operations. The service accepts
requests during warmup. A first-ever uncached request still waits for S3.

Cache keys include the bucket, endpoint, and filename. Removing files from the
cache directory forces subsequent requests to reload them. To clear the Docker
cache, stop the service and remove only its thumbnail volume, then start it again.
Do not delete the configuration mount. Replacing an original image also requires
removing its stored `thumbs/` object to regenerate the thumbnail.

Successful images and thumbnails advertise `public, max-age=86400`. Cloudflare
and browsers can retain a previous version for that duration after an image is
changed. Local caching accelerates origin requests when an edge cache is cold;
it does not require a Cloudflare cache purge or configuration change.

`MEMES_API_CONFIG` selects an explicit JSON configuration file. Otherwise the
usual working-directory, user-config, and `/etc` locations apply.

## Testing

Run the repository checks with Docker available:

    mise run check

The S3 integration tests use testcontainers to start
`localstack/localstack:4.14.0` with S3 enabled. Each test gets a separate bucket
and temporary cache directory. Only dummy credentials and the container's mapped
HTTP endpoint are used. Docker or LocalStack startup failures fail the tests;
they are not skipped. No production S3 configuration is loaded by the test suite.

The GitHub Actions test job runs the same suite on its Docker-capable Ubuntu
runner. After deploying, compare thumbnail requests with `CF-Cache-Status: HIT`
and `MISS` and inspect browser paging; local tests do not establish live-site
performance.
