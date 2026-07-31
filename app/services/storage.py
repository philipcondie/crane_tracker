import logging
from functools import lru_cache
from typing import Any, BinaryIO
from urllib.parse import quote

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.exceptions import PhotoStorageError

logger = logging.getLogger(__name__)


def _get_r2_config() -> tuple[str, str, str, str]:
    settings = get_settings()
    values = {
        "R2_ENDPOINT_URL": settings.r2_endpoint_url,
        "R2_ACCESS_KEY_ID": settings.r2_access_key_id,
        "R2_SECRET_ACCESS_KEY": settings.r2_secret_access_key,
        "R2_BUCKET_NAME": settings.r2_bucket_name,
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        logger.error(
            "photo_storage_configuration_missing",
            extra={"missing_settings": missing},
        )
        raise PhotoStorageError("Photo storage is not configured")

    return (
        values["R2_ENDPOINT_URL"],
        values["R2_ACCESS_KEY_ID"],
        values["R2_SECRET_ACCESS_KEY"],
        values["R2_BUCKET_NAME"],
    )


@lru_cache(maxsize=1)
def _get_s3_client() -> Any:
    endpoint_url, access_key_id, secret_access_key, _ = _get_r2_config()
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )


def upload_photo(
    file: BinaryIO,
    *,
    object_key: str,
    content_type: str,
) -> None:
    """Upload a photo to Cloudflare R2."""
    _, _, _, bucket = _get_r2_config()
    client = _get_s3_client()

    try:
        client.upload_fileobj(
            file,
            bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
    except (BotoCoreError, ClientError) as e:
        logger.exception(
            "photo_storage_upload_failed",
            extra={"bucket": bucket, "object_key": object_key},
        )
        raise PhotoStorageError("Photo could not be stored") from e

    logger.info(
        "photo_storage_upload_succeeded",
        extra={"bucket": bucket, "object_key": object_key},
    )


def delete_photo(*, object_key: str) -> None:
    """Delete a photo from Cloudflare R2."""
    _, _, _, bucket = _get_r2_config()
    client = _get_s3_client()

    try:
        client.delete_object(Bucket=bucket, Key=object_key)
    except (BotoCoreError, ClientError) as e:
        logger.exception(
            "photo_storage_delete_failed",
            extra={"bucket": bucket, "object_key": object_key},
        )
        raise PhotoStorageError("Photo could not be deleted") from e

    logger.info(
        "photo_storage_delete_succeeded",
        extra={"bucket": bucket, "object_key": object_key},
    )


def get_public_url(*, object_key: str) -> str:
    """Derive an object's URL from the current public R2 domain."""
    public_base_url = get_settings().r2_public_base_url
    if not public_base_url:
        logger.error(
            "photo_storage_configuration_missing",
            extra={"missing_settings": ["R2_PUBLIC_BASE_URL"]},
        )
        raise PhotoStorageError("Photo storage is not configured")

    encoded_key = quote(object_key, safe="/")
    return f"{public_base_url.rstrip('/')}/{encoded_key}"
