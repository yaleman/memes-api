"""config things"""

from functools import lru_cache
from typing import Optional
from pathlib import Path

from pydantic import BaseModel


class MemeConfig(BaseModel):
    """config file"""

    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    bucket: str
    baseurl: str
    endpoint_url: Optional[str]


CONFIG_FILES = [
    "~/.config/memes-api.json",
    "memes-api.json",
    "/etc/memes-api.json",
]


@lru_cache()
def meme_config_load(
    filepath: Optional[Path] = None,
) -> MemeConfig:
    """Config loader, returns a pydantic object, will try the following in order, returning the result of parsing the first one found.

    - `~/.config/memes-api.json`
    - `memes-api.json`
    - `/etc/memes-api.json`
    """

    if filepath is not None:
        if not isinstance(filepath, Path):
            filepath = Path(filepath)
        if filepath.exists():
            return MemeConfig.model_validate_json(filepath.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"Couldn't find config at {filepath}")
    for testpath in CONFIG_FILES:
        filepath = Path(testpath).expanduser().resolve()
        if filepath.exists():
            return MemeConfig.model_validate_json(filepath.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Couldn't find config at {CONFIG_FILES}")
