""" session things """

import aioboto3  # type: ignore

from .config import meme_config_load


def get_aioboto3_session() -> aioboto3.Session:
    """gets a session"""
    meme_config = meme_config_load()
    return aioboto3.Session(
        aws_access_key_id=meme_config.aws_access_key_id,
        aws_secret_access_key=meme_config.aws_secret_access_key,
        region_name=meme_config.aws_region,
    )
