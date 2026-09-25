from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from minio.error import MinioException
from urllib3.exceptions import HTTPError

from sanaap_backend_challenge_api.documents.models import File
from sanaap_backend_challenge_api.documents.services import purge_deleted_file
from sanaap_backend_challenge_api.documents.storage import get_minio_client


class Command(BaseCommand):
    help = "Permanently remove soft-deleted objects after the retention window."

    def handle(self, *args, **options):
        client = get_minio_client()
        try:
            if client.get_bucket_versioning(settings.MINIO_BUCKET).status is not None:
                raise CommandError(
                    "Cleanup requires an unversioned bucket; version-aware purging is not implemented."
                )
        except (MinioException, HTTPError, OSError) as exc:
            raise CommandError(
                "Cannot check bucket versioning; no files purged."
            ) from exc
        cutoff = timezone.now() - timedelta(days=settings.FILE_RETENTION_DAYS)
        ids = (
            File.objects.filter(deleted_at__lte=cutoff, purged_at__isnull=True)
            .values_list("pk", flat=True)
            .iterator(chunk_size=100)
        )
        purged = failed = 0
        for document_id in ids:
            try:
                purged += purge_deleted_file(document_id, cutoff=cutoff, client=client)
            except (MinioException, HTTPError, OSError):
                failed += 1
                self.stderr.write(
                    f"Storage cleanup failed for {document_id}; retry on next run."
                )
        self.stdout.write(f"Purged {purged} file(s); failed {failed}.")
        if failed:
            raise CommandError("Some files could not be purged; rerun to retry.")
