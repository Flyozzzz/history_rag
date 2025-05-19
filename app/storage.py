import aioboto3
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

settings = get_settings()
session = aioboto3.Session()

async def upload_file(obj: bytes, key: str, content_type: str) -> str:
    async with session.client(
        "s3",
        endpoint_url=f"http://{settings.minio_endpoint}",
        aws_secret_access_key=settings.minio_secret_key,
        aws_access_key_id=settings.minio_access_key,
    ) as s3:
        bucket = settings.minio_bucket
        # Ensure bucket exists
        try:
            await s3.head_bucket(Bucket=bucket)
        except s3.exceptions.NoSuchBucket:
            await s3.create_bucket(Bucket=bucket)
        try:
            await s3.put_object(Bucket=bucket, Key=key, Body=obj, ContentType=content_type)
        except Exception as exc:
            logger.exception("Failed to upload %s", key)
            raise
        return f"http://{settings.minio_endpoint}/{bucket}/{key}"
