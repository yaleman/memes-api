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
    twitter_handle: Optional[str] = None

    @classmethod
    def default(cls) -> "MemeConfig":
        """Load config from the default locations"""
        for testpath in CONFIG_FILES:
            filepath = Path(testpath).expanduser().resolve()
            if filepath.exists():
                return MemeConfig.model_validate_json(
                    filepath.read_text(encoding="utf-8")
                )
        raise FileNotFoundError(f"Couldn't find config at {CONFIG_FILES}")


CONFIG_FILES = [
    "memes-api.json",
    "~/.config/memes-api.json",
    "/etc/memes-api.json",
]


@lru_cache(maxsize=1, typed=True)
def meme_config_load(
    filepath: Optional[Path] = None,
) -> MemeConfig:
    """Config loader, returns a pydantic object, will try the following in order, returning the result of parsing the first one found.

    - `memes-api.json`
    - `~/.config/memes-api.json`
    - `/etc/memes-api.json`
    """
    if filepath is not None:
        if filepath.exists():
            result = MemeConfig.model_validate_json(
                filepath.read_text(encoding="utf-8")
            )
            return result
        raise FileNotFoundError(f"Couldn't find config at {filepath}")
    for testpath in CONFIG_FILES:
        filepath = Path(testpath).expanduser().resolve()
        if filepath.exists():
            result = MemeConfig.model_validate_json(
                filepath.read_text(encoding="utf-8")
            )
            return result
    raise FileNotFoundError(f"Couldn't find config at {CONFIG_FILES}")
