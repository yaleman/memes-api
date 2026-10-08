"""config things"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class MemeConfig(BaseModel):
    """config file"""

    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    bucket: str
    baseurl: str
    endpoint_url: str | None
    thumbnail_cache_dir: Path = Path("~/.cache/memes-api/thumbnails")

    def load_from_file(self, filepath: Path) -> None:
        """load from a file"""
        newvals = MemeConfig.model_validate_json(filepath.read_text(encoding="utf-8"))
        for field in MemeConfig.model_fields:
            setattr(self, field, getattr(newvals, field))

    @classmethod
    def default(cls) -> "MemeConfig":
        """Load config from the default locations"""
        for testpath in config_files():
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


def config_files() -> list[str]:
    """Allow explicit configuration without relying on the working directory."""
    explicit = os.environ.get("MEMES_API_CONFIG")
    return [explicit] if explicit else CONFIG_FILES


@lru_cache
def meme_config_load(
    filepath: Path | None = None,
) -> MemeConfig:
    """Config loader, returns a pydantic object, will try the following in order, returning the result of parsing the first one found.

    - `memes-api.json`
    - `~/.config/memes-api.json`
    - `/etc/memes-api.json`
    """

    if filepath is not None:
        if not isinstance(filepath, Path):
            filepath = Path(filepath)
        if filepath.exists():
            return MemeConfig.model_validate_json(filepath.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"Couldn't find config at {filepath}")
    for testpath in config_files():
        filepath = Path(testpath).expanduser().resolve()
        if filepath.exists():
            return MemeConfig.model_validate_json(filepath.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Couldn't find config at {CONFIG_FILES}")
