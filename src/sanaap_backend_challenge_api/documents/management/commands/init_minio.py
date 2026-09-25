from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from minio.commonconfig import ENABLED, Filter
from minio.error import S3Error
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule
from urllib3.exceptions import HTTPError

from sanaap_backend_challenge_api.documents.storage import get_minio_client


class Command(BaseCommand):
    help = "Create the configured private MinIO bucket if it does not exist."

    def add_arguments(self, parser):
        parser.add_argument("--configure-upload-lifecycle", action="store_true")

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
            if options["configure_upload_lifecycle"]:
                if client.get_bucket_versioning(bucket).status is not None:
                    raise CommandError(
                        "Upload lifecycle setup requires an unversioned bucket."
                    )
                lifecycle = client.get_bucket_lifecycle(bucket)
                rules = lifecycle.rules if lifecycle is not None else []
                rule_id = "sanaap-staging-uploads"
                rules = [rule for rule in rules if rule.rule_id != rule_id]
                rules.append(
                    Rule(
                        ENABLED,
                        rule_id=rule_id,
                        rule_filter=Filter(prefix="uploads/"),
                        expiration=Expiration(
                            days=settings.MINIO_STAGING_EXPIRATION_DAYS
                        ),
                    )
                )
                client.set_bucket_lifecycle(bucket, LifecycleConfig(rules))
        except (S3Error, HTTPError) as exc:
            raise CommandError(
                "Cannot initialize MinIO; check service and credentials."
            ) from exc
        self.stdout.write(
            self.style.SUCCESS("MinIO bucket is ready (no public policy).")
        )
