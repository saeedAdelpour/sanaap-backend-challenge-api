from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from minio.commonconfig import CopySource
from minio.error import MinioException, S3Error
from rest_framework.exceptions import APIException, ValidationError
from urllib3.exceptions import HTTPError

from sanaap_backend_challenge_api.documents.models import File
from sanaap_backend_challenge_api.documents.storage import get_minio_client


class StorageUnavailable(APIException):
    status_code = 503
    default_detail = "File storage is unavailable. Please try again."
    default_code = "storage_unavailable"


def initiate_upload(*, original_name, size_bytes, title=None):
    document = File(
        title=title or original_name,
        original_name=original_name,
        storage_key=f"uploads/{uuid4().hex}",
        content_type="application/octet-stream",
        size_bytes=size_bytes,
    )
    try:
        url = get_minio_client().presigned_put_object(
            settings.MINIO_BUCKET,
            document.storage_key,
            expires=timedelta(seconds=settings.MINIO_UPLOAD_URL_TTL),
        )
    except (MinioException, HTTPError, OSError) as exc:
        raise StorageUnavailable from exc
    document.save()
    return document, url


@transaction.atomic
def complete_upload(document_id):
    # Serialize completion requests so a ready file cannot be replaced.
    document = File.objects.select_for_update().get(pk=document_id)
    if document.status == File.Status.READY:
        return document
    if document.status != File.Status.PENDING:
        raise ValidationError("This upload cannot be completed.")

    client = get_minio_client()
    bucket = settings.MINIO_BUCKET
    try:
        source = client.stat_object(bucket, document.storage_key)
        if source.size != document.size_bytes:
            raise ValidationError({"size_bytes": "Uploaded size does not match."})
        # The PUT URL remains reusable until expiry. Publish a separate key so
        # reuse cannot overwrite the completed document. Match the checked ETag.
        final_key = f"documents/{document.pk.hex}"
        client.copy_object(
            bucket,
            final_key,
            CopySource(bucket, document.storage_key, match_etag=source.etag),
            metadata={"Content-Type": "application/octet-stream"},
            metadata_directive="REPLACE",
        )
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "PreconditionFailed"}:
            raise ValidationError(
                "Upload is missing or changed during completion. Upload and retry."
            ) from exc
        raise StorageUnavailable from exc
    except (MinioException, HTTPError, OSError) as exc:
        raise StorageUnavailable from exc

    document.storage_key = final_key
    document.status = File.Status.READY
    document.save(update_fields=["storage_key", "status", "updated_at"])
    return document


def get_download_url(document_id):
    document = File.objects.get(pk=document_id)
    if document.status != File.Status.READY:
        raise ValidationError("This download cannot be completed.")

    try:
        url = get_minio_client().presigned_get_object(
            settings.MINIO_BUCKET,
            document.storage_key,
            expires=timedelta(seconds=settings.MINIO_UPLOAD_URL_TTL),
        )
    except (MinioException, HTTPError, OSError) as exc:
        raise StorageUnavailable from exc
    return document, url
