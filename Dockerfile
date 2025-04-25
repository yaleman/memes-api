FROM python:3.13-slim

WORKDIR /code

COPY ./uv.lock /code/uv.lock
COPY ./pyproject.toml /code/pyproject.toml

RUN python -m pip install --upgrade pip uv
COPY ./memes_api/ /code/memes_api/
RUN python -m pip install /code/

RUN rm -rf /code

RUN adduser --disabled-password --gecos "" --home /home/memes memes

# allow xff from anywhere, because we're in docker
ENV FORWARDED_ALLOW_IPS="*"

USER memes

CMD ["memes-api", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
