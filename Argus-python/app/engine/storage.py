import io
import logging
from typing import List

from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)


class MinioStorageService:
    def __init__(self):
        endpoint = settings.minio.endpoint
        self.client = Minio(
            endpoint=endpoint,
            access_key=settings.minio.access_key,
            secret_key=settings.minio.secret_key,
            secure=settings.minio.secure,
        )
        self.bucket = settings.minio.bucket
        self._ready_buckets: set[str] = set()
        logger.info("MinIO initialized: endpoint=%s, bucket=%s", endpoint, self.bucket)

    def _ensure_bucket(self, bucket: str) -> None:
        if bucket in self._ready_buckets:
            return
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)
            logger.info("Created MinIO bucket: %s", bucket)
        self._ready_buckets.add(bucket)

    def upload(self, object_key: str, data: bytes, content_type: str, bucket: str | None = None) -> None:
        bucket = bucket or self.bucket
        try:
            self._ensure_bucket(bucket)
            self.client.put_object(
                bucket, object_key, io.BytesIO(data), len(data), content_type=content_type
            )
        except S3Error as e:
            raise RuntimeError(f"MinIO upload failed: {e}")

    def download(self, object_key: str, bucket: str | None = None) -> bytes:
        bucket = bucket or self.bucket
        try:
            response = self.client.get_object(bucket, object_key)
            return response.read()
        except S3Error as e:
            raise RuntimeError(f"MinIO download failed: {e}")

    def delete(self, object_key: str, bucket: str | None = None) -> None:
        bucket = bucket or self.bucket
        try:
            self.client.remove_object(bucket, object_key)
        except S3Error as e:
            raise RuntimeError(f"MinIO delete failed: {e}")

    def compose(self, target_key: str, source_keys: List[str], content_type: str, bucket: str | None = None) -> None:
        bucket = bucket or self.bucket
        if not source_keys:
            raise RuntimeError("No source keys for compose")
        try:
            from minio.commonconfig import ComposeSource
            sources = [ComposeSource(bucket, k) for k in source_keys]
            result = self.client.compose_object(bucket, target_key, sources)
            logger.info("Composed MinIO object: bucket=%s, target=%s, sources=%d", bucket, target_key, len(source_keys))
        except S3Error as e:
            raise RuntimeError(f"MinIO compose failed: {e}")


storage_service = MinioStorageService()
