FROM python:3.14-slim

WORKDIR /code

COPY ./uv.lock /code/uv.lock
COPY ./pyproject.toml /code/pyproject.toml

RUN python -m pip install --upgrade uv
COPY ./memes_api/ /code/memes_api/
ADD README.md /code/README.md
RUN python -m pip install /code/

RUN rm -rf /code

RUN adduser --disabled-password --gecos "" --home /home/memes memes

# allow xff from anywhere, because we're in docker
ENV FORWARDED_ALLOW_IPS="*"

RUN mkdir -p /home/memes/.cache/memes-api/thumbnails && chown -R memes:memes /home/memes/.cache

USER memes

CMD ["memes-api", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
