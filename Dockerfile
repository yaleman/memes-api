FROM python:3.10-slim

WORKDIR /code

COPY ./poetry.lock /code/poetry.lock
COPY ./pyproject.toml /code/pyproject.toml

RUN python -m pip install --upgrade pip poetry
COPY ./memes_api/ /code/memes_api/
RUN python -m pip install /code/

RUN rm -rf /code

# allow xff from anywhere, because we're in docker
ENV FORWARDED_ALLOW_IPS="*"

CMD ["memes-api", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
