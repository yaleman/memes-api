FROM python:3.10

WORKDIR /code

COPY ./poetry.lock /code/poetry.lock
COPY ./pyproject.toml /code/pyproject.toml

RUN python -m pip install --upgrade pip poetry
RUN poetry config virtualenvs.in-project false
RUN poetry install

#
COPY ./memes_api/ /code/memes_api/

#
CMD ["poetry", "run", "python", "-m", "memes_api", "--host", "0.0.0.0", "--port", "8000"]