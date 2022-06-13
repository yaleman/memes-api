""" cleans up filenames to remove spaces because s3 is sassy """
import asyncio
import sys
from typing import List

import aioboto3 #type: ignore
from botocore.exceptions import ClientError
import click

from .config import meme_config_load, MemeConfig
from .constants import THUMBNAIL_BUCKET_PREFIX


async def get_image_list(
    meme_config: MemeConfig,
    session: aioboto3.Session,
    ) -> List[str]:
    """ pulls the list of images """
    if meme_config.endpoint_url is not None:
        async with session.resource(
            "s3", endpoint_url=meme_config.endpoint_url
        ) as s3_resource:
            bucket = await s3_resource.Bucket(meme_config.bucket)
            results = [
                    image.key
                    async for image in bucket.objects.iterator()
                    if not image.key.startswith(THUMBNAIL_BUCKET_PREFIX)
            ]
    else:
        async with session.resource("s3") as s3_resource:
            bucket = await s3_resource.Bucket(meme_config.bucket)
            results = [
                    image.key
                    async for image in bucket.objects.iterator()
                    if not image.key.startswith(THUMBNAIL_BUCKET_PREFIX)
            ]
    return results

async def rename_image(
    meme_config: MemeConfig,
    session: aioboto3.Session,
    image_name: str,
) -> bool:
    """ renames an image to remove spaces from the filename """
    target_name = image_name.replace(" ", "-")
    while '--' in target_name:
        target_name = target_name.replace('--', '-')

    print(f"Renaming {image_name} to {target_name}")

    async with session.client("s3", endpoint_url=meme_config.endpoint_url) as s3_object:
        try:
            result = await s3_object.head_object(
                Key=target_name,
                Bucket=meme_config.bucket,
                )
            print(f"Target file {target_name} exists")
            sys.exit(1)
        except ClientError as failed:
            if hasattr(failed, "response"):
                response = getattr(failed, "response")
                if "Error" in response:
                    error = response['Error']
                    if error["Code"] != "404":
                        print(f"head_object error: {failed}")
                        return False
        try:
            copy_source = {
               'Bucket': meme_config.bucket,
                'Key': image_name
            }
            result = await s3_object.copy_object(
                CopySource=copy_source,
                Bucket=meme_config.bucket,
                Key=target_name,
            )
            print(f"copy_object {result=}")
        except ClientError as client_error:
            print(f"failed to copy {image_name} to {target_name}:\n{client_error}")
            sys.exit(1)
        try:
            result = await s3_object.delete_object(**copy_source)
            print(f"delete_object {result=}")
        except ClientError as client_error:
            print(f"failed to delete {image_name}:\n{client_error}")
            sys.exit(1)
    return True

@click.command()
def cli() -> None:
    """ Looks in the configured bucket to make sure all images have s3-compliant filenames """

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
