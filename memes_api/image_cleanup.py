"""cleans up filenames to remove spaces because s3 is sassy"""

import asyncio
import logging
from typing import List

import aioboto3
from botocore.exceptions import ClientError
import click

from .config import meme_config_load, MemeConfig
from .s3_utils import list_images

logger = logging.getLogger(__name__)


async def get_image_list(
    meme_config: MemeConfig,
    session: aioboto3.Session,
) -> List[str]:
    """pulls the list of images"""
    return await list_images(session, meme_config)


async def rename_image(
    meme_config: MemeConfig,
    session: aioboto3.Session,
    image_name: str,
) -> bool:
    """renames an image to remove spaces from the filename"""
    target_name = image_name.replace(" ", "-")
    while "--" in target_name:
        target_name = target_name.replace("--", "-")

    logging.info("Renaming %s to %s", image_name, target_name)

    async with session.client("s3", endpoint_url=meme_config.endpoint_url) as s3_object:
        try:
            await s3_object.head_object(Key=target_name, Bucket=meme_config.bucket)
            logging.info("Target file %s exists, skipping", target_name)
            return False
        except ClientError as failed:
            if failed.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey"):
                logging.error("head_object error: %s", failed)
                return False
        try:
            copy_source = {"Bucket": meme_config.bucket, "Key": image_name}
            result = await s3_object.copy_object(
                CopySource=copy_source,
                Bucket=meme_config.bucket,
                Key=target_name,
            )
            logging.info("copy_object result: %s", result)
        except ClientError as client_error:
            logging.error("failed to copy %s to %s: %s", image_name, target_name, client_error)
            return False
        try:
            result = await s3_object.delete_object(**copy_source)
            logging.info("delete_object result: %s", result)
        except ClientError as client_error:
            logging.error("failed to delete %s: %s", image_name, client_error)
            return False
    return True


@click.command()
def cli() -> None:
    """Looks in the configured bucket to make sure
    all images have s3-compliant filenames
    """

    meme_config = meme_config_load()
    session = aioboto3.Session(
        aws_access_key_id=meme_config.aws_access_key_id,
        aws_secret_access_key=meme_config.aws_secret_access_key,
        region_name=meme_config.aws_region,
    )
    loop = asyncio.new_event_loop()

    images = loop.run_until_complete(get_image_list(meme_config, session))

    for image in images:
        if " " in image:
            loop.run_until_complete(rename_image(meme_config, session, image))


if __name__ == "__main__":
    cli()
