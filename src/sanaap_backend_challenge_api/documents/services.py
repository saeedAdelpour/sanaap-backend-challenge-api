from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import content_disposition_header
from minio.commonconfig import CopySource
from minio.error import MinioException, S3Error
from rest_framework.exceptions import APIException, ValidationError
from urllib3.exceptions import HTTPError

from sanaap_backend_challenge_api.documents.models import File, FileReplacement
from sanaap_backend_challenge_api.documents.storage import get_minio_client


class StorageUnavailable(APIException):
    status_code = 503
    default_detail = "File storage is unavailable. Please try again."
    default_code = "storage_unavailable"


def initiate_upload(*, original_name, size_bytes, uploaded_by, title=None):
    document = File(
        title=title or original_name,
        original_name=original_name,
        storage_key=f"uploads/{uuid4().hex}",
        content_type="application/octet-stream",
        size_bytes=size_bytes,
        uploaded_by=uploaded_by,
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
    document = get_object_or_404(
        File.objects.select_for_update(), pk=document_id, deleted_at__isnull=True
    )
    if document.status == File.Status.READY:
        return document
    if document.status != File.Status.PENDING:
        raise ValidationError("This upload cannot be completed.")

    _check_completion_deadline(document.created_at)
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


@transaction.atomic
def get_download_url(document_id):
    document = get_object_or_404(
        File.objects.select_for_update(), pk=document_id, deleted_at__isnull=True
    )
    if document.status != File.Status.READY:
        raise ValidationError("This download cannot be completed.")

    try:
        url = get_minio_client().presigned_get_object(
            settings.MINIO_BUCKET,
            document.storage_key,
            expires=timedelta(seconds=settings.MINIO_UPLOAD_URL_TTL),
            response_headers={
                "response-content-disposition": content_disposition_header(
                    as_attachment=True, filename=document.original_name
                ),
            },
        )
    except (MinioException, HTTPError, OSError) as exc:
        raise StorageUnavailable from exc
    return document, url


class ReplacementConflict(APIException):
    status_code = 409
    default_detail = (
        "The file changed after this replacement started. Start a new replacement."
    )
    default_code = "replacement_conflict"


@transaction.atomic
def update_file_metadata(document_id, **changes):
    document = get_object_or_404(
        File.objects.select_for_update(), pk=document_id, deleted_at__isnull=True
    )
    for field in ("title", "original_name"):
        if field in changes:
            setattr(document, field, changes[field])
    if changes:
        document.save(update_fields=[*changes, "updated_at"])
    return document


@transaction.atomic
def initiate_replacement(document_id, *, original_name, size_bytes):
    document = get_object_or_404(
        File.objects.select_for_update(), pk=document_id, deleted_at__isnull=True
    )
    if document.status != File.Status.READY:
        raise ValidationError("Only ready files can be replaced.")
    replacement = FileReplacement(
        file=document,
        original_name=original_name,
        size_bytes=size_bytes,
        previous_storage_key=document.storage_key,
    )
    try:
        url = get_minio_client().presigned_put_object(
            settings.MINIO_BUCKET,
            replacement.storage_key,
            expires=timedelta(seconds=settings.MINIO_UPLOAD_URL_TTL),
        )
    except (MinioException, HTTPError, OSError) as exc:
        raise StorageUnavailable from exc
    replacement.save()
    return replacement, url


@transaction.atomic
def complete_replacement(document_id, *, replacement_id):
    document = get_object_or_404(
        File.objects.select_for_update(), pk=document_id, deleted_at__isnull=True
    )
    replacement = get_object_or_404(
        FileReplacement, pk=replacement_id, file_id=document_id
    )
    if replacement.completed_at:
        return document
    if (
        document.status != File.Status.READY
        or document.storage_key != replacement.previous_storage_key
    ):
        raise ReplacementConflict

    _check_completion_deadline(replacement.created_at)
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET
    final_key = f"documents/{document.pk.hex}/{replacement.pk.hex}"
    try:
        source = client.stat_object(bucket, replacement.storage_key)
        if source.size != replacement.size_bytes:
            raise ValidationError({"size_bytes": "Uploaded size does not match."})
        client.copy_object(
            bucket,
            final_key,
            CopySource(bucket, replacement.storage_key, match_etag=source.etag),
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
    document.original_name = replacement.original_name
    document.size_bytes = replacement.size_bytes
    document.content_type = "application/octet-stream"
    document.save(
        update_fields=[
            "storage_key",
            "original_name",
            "size_bytes",
            "content_type",
            "updated_at",
        ]
    )
    replacement.completed_at = timezone.now()
    replacement.save(update_fields=["completed_at"])
    return document


def _check_completion_deadline(created_at):
    if timezone.now() >= created_at + timedelta(
        seconds=settings.FILE_UPLOAD_COMPLETION_TTL
    ):
        raise ValidationError(
            "Upload completion deadline has passed. Start a new upload."
        )


@transaction.atomic
def soft_delete_file(document_id, *, deleted_by):
    document = get_object_or_404(
        File.objects.select_for_update(), pk=document_id, deleted_at__isnull=True
    )
    document.deleted_at = timezone.now()
    document.deleted_by = deleted_by
    document.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
    return document


@transaction.atomic
def purge_deleted_file(document_id, *, cutoff, client):
    """Retry-safe for unversioned buckets; preserve metadata as an audit record."""
    document = File.objects.select_for_update().get(pk=document_id)
    if (
        document.deleted_at is None
        or document.deleted_at > cutoff
        or document.purged_at
    ):
        return False
    keys = {document.storage_key, f"documents/{document.pk.hex}"}
    for replacement in document.replacements.all():
        keys.update(
            {
                replacement.storage_key,
                replacement.previous_storage_key,
                f"documents/{document.pk.hex}/{replacement.pk.hex}",
            }
        )
    for key in sorted(keys):
        try:
            client.remove_object(settings.MINIO_BUCKET, key)
        except S3Error as exc:
            if exc.code not in {"NoSuchKey", "NoSuchObject"}:
                raise
    document.purged_at = timezone.now()
    document.save(update_fields=["purged_at", "updated_at"])
    return True
