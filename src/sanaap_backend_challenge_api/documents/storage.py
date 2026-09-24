"""MinIO client construction; no network calls during Django startup."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from minio import Minio
from urllib3 import PoolManager, Retry, Timeout


def get_minio_client():
    if not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
        raise ImproperlyConfigured("Set MINIO_ACCESS_KEY and MINIO_SECRET_KEY.")
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        http_client=PoolManager(
            timeout=Timeout(connect=5, read=30),
            retries=Retry(total=2, backoff_factor=0.2),
        ),
    )
