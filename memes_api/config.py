""" config things """

from functools import lru_cache
from typing import Optional
from pathlib import Path

from pydantic import BaseModel

class MemeConfig(BaseModel):
    """ config file """
    aws_access_key_id : str
    aws_secret_access_key : str
    aws_region: str
    bucket: str
    baseurl: str
    endpoint_url: Optional[str]

@lru_cache()
def meme_config_load(filepath: Optional[Path]=None) -> MemeConfig:
    """ config loader, returns a pydantic object, will try ~/.config/memes-api.json, memes-api.json, /etc/memes-api.json in order, returning the result of parsing the first one found. """
    if filepath is not None:
        if filepath.exists():
            return MemeConfig.parse_file(filepath.expanduser().resolve())
        raise FileNotFoundError(f"Couldn't find {filepath}")
    for testpath in [
        "~/.config/memes-api.json",
        "memes-api.json",
        "/etc/memes-api.json",
    ]:
        filepath = Path(testpath).expanduser().resolve()
        if filepath.exists():
            return MemeConfig.parse_file(filepath.expanduser().resolve())
    raise FileNotFoundError(f"Couldn't find {filepath}")
