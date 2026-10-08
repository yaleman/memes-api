"""session things"""

import logging

import aioboto3

from .config import MemeConfig

LOGGER = logging.getLogger(__name__)


def get_aioboto3_session(meme_config: MemeConfig) -> aioboto3.Session:
    """gets a session"""
    LOGGER.debug("Creating S3 session")
    return aioboto3.Session(
        aws_access_key_id=meme_config.aws_access_key_id,
        aws_secret_access_key=meme_config.aws_secret_access_key,
        region_name=meme_config.aws_region,
    )
