from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from minio.error import S3Error
from urllib3.exceptions import HTTPError

from sanaap_backend_challenge_api.documents.storage import get_minio_client


class Command(BaseCommand):
    help = "Create the configured private MinIO bucket if it does not exist."

    def handle(self, *args, **options):
        client = get_minio_client()
        bucket = settings.MINIO_BUCKET
        try:
            if not client.bucket_exists(bucket):
                try:
                    client.make_bucket(bucket)
                except S3Error as exc:
                    if exc.code != "BucketAlreadyOwnedByYou":
                        raise
            # New buckets are private. Refuse an existing policy rather than
            # silently changing permissions on an existing bucket.
            try:
                client.get_bucket_policy(bucket)
            except S3Error as exc:
                if exc.code != "NoSuchBucketPolicy":
                    raise
            else:
                raise CommandError(
                    "Bucket has an existing access policy. Review it before use."
                )
        except (S3Error, HTTPError) as exc:
            raise CommandError(
                "Cannot initialize MinIO; check service and credentials."
            ) from exc
        self.stdout.write(
            self.style.SUCCESS("MinIO bucket is ready (no public policy).")
        )
