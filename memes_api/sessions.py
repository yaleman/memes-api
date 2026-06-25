"""session things"""

import logging
import aioboto3
from .config import MemeConfig


def get_aioboto3_session(meme_config: MemeConfig) -> aioboto3.Session:
    """gets a session"""
    logging.debug("Getting aioboto3 session meme_config=%s", meme_config)
    return aioboto3.Session(
        aws_access_key_id=meme_config.aws_access_key_id,
        aws_secret_access_key=meme_config.aws_secret_access_key,
        region_name=meme_config.aws_region,
    )
