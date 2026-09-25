from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import Http404
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from minio.commonconfig import ENABLED, Filter
from minio.error import S3Error
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule
from rest_framework.test import APITestCase
from urllib3.exceptions import HTTPError

from sanaap_backend_challenge_api.documents import services
from sanaap_backend_challenge_api.documents.models import File, FileReplacement


class DeletionTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="deleter")
        self.user.groups.add(Group.objects.get(name="Admin"))
        self.client.force_authenticate(self.user)
        self.document = File.objects.create(
            title="Policy",
            original_name="policy.pdf",
            size_bytes=4,
            content_type="application/octet-stream",
            storage_key="documents/current",
            status=File.Status.READY,
        )
        self.url = reverse("file-detail", args=[self.document.pk])

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_delete_hides_file_and_preserves_audit_and_bytes(self, get_client):
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.document.refresh_from_db()
        deleted_at = self.document.deleted_at
        self.assertIsNotNone(deleted_at)
        self.assertEqual(self.document.deleted_by, self.user)
        self.assertIsNone(self.document.purged_at)
        self.assertEqual(self.document.status, File.Status.READY)
        self.assertEqual(self.client.get(reverse("file-list")).data["count"], 0)
        for method, name, data in [
            ("get", "file-detail", {}),
            ("delete", "file-detail", {}),
            ("patch", "file-detail", {"title": "changed"}),
            ("get", "file-download", {}),
            ("post", "file-complete", {}),
            ("post", "file-replace", {"original_name": "new", "size_bytes": 4}),
            (
                "post",
                "file-complete-replacement",
                {"replacement_id": str(self.document.pk)},
            ),
        ]:
            with self.subTest(method=method, name=name):
                response = getattr(self.client, method)(
                    reverse(name, args=[self.document.pk]), data, format="json"
                )
                self.assertEqual(response.status_code, 404)
        self.document.refresh_from_db()
        self.assertEqual(self.document.deleted_at, deleted_at)
        get_client.assert_not_called()

    def test_viewer_cannot_delete(self):
        self.user.groups.set([Group.objects.get(name="Viewer")])
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        self.document.refresh_from_db()
        self.assertIsNone(self.document.deleted_at)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_services_recheck_deletion_after_view_lookup(self, get_client):
        services.soft_delete_file(self.document.pk, deleted_by=self.user)
        operations = [
            lambda: services.complete_upload(self.document.pk),
            lambda: services.get_download_url(self.document.pk),
            lambda: services.update_file_metadata(self.document.pk, title="changed"),
            lambda: services.initiate_replacement(
                self.document.pk, original_name="new", size_bytes=4
            ),
            lambda: services.complete_replacement(
                self.document.pk, replacement_id=self.document.pk
            ),
        ]
        for operation in operations:
            with self.assertRaises(Http404):
                operation()
        get_client.assert_not_called()

    @override_settings(FILE_RETENTION_DAYS=30)
    @patch(
        "sanaap_backend_challenge_api.documents.management.commands.purge_deleted_files.get_minio_client"
    )
    def test_retention_boundary_and_active_files(self, get_client):
        client = get_client.return_value
        client.get_bucket_versioning.return_value.status = None
        now = timezone.now()
        call_command("purge_deleted_files", stdout=StringIO())
        client.remove_object.assert_not_called()
        self.document.deleted_at = now - timedelta(days=30) + timedelta(seconds=1)
        self.document.save()
        with patch("django.utils.timezone.now", return_value=now):
            call_command("purge_deleted_files", stdout=StringIO())
            client.remove_object.assert_not_called()
            self.document.deleted_at = now - timedelta(days=30)
            self.document.save()
            call_command("purge_deleted_files", stdout=StringIO())
        self.document.refresh_from_db()
        self.assertEqual(self.document.purged_at, now)
        client.remove_object.reset_mock()
        call_command("purge_deleted_files", stdout=StringIO())
        client.remove_object.assert_not_called()

    @patch(
        "sanaap_backend_challenge_api.documents.management.commands.purge_deleted_files.get_minio_client"
    )
    def test_partial_storage_failure_retries_all_related_keys(self, get_client):
        client = get_client.return_value
        client.get_bucket_versioning.return_value.status = None
        replacement = FileReplacement.objects.create(
            file=self.document,
            original_name="new",
            size_bytes=4,
            previous_storage_key="documents/previous",
        )
        self.document.deleted_at = timezone.now() - timedelta(days=31)
        self.document.save()
        client.remove_object.side_effect = [None, HTTPError("offline")]
        with self.assertRaises(CommandError):
            call_command("purge_deleted_files", stdout=StringIO(), stderr=StringIO())
        self.document.refresh_from_db()
        self.assertIsNone(self.document.purged_at)
        client.remove_object.reset_mock()
        client.remove_object.side_effect = S3Error(
            response=None,
            code="NoSuchKey",
            message="missing",
            resource="resource",
            request_id="request",
            host_id="host",
        )
        call_command("purge_deleted_files", stdout=StringIO())
        self.document.refresh_from_db()
        self.assertIsNotNone(self.document.purged_at)
        self.assertEqual(
            {call.args[1] for call in client.remove_object.call_args_list},
            {
                self.document.storage_key,
                f"documents/{self.document.pk.hex}",
                replacement.previous_storage_key,
                replacement.storage_key,
                f"documents/{self.document.pk.hex}/{replacement.pk.hex}",
            },
        )

    @patch(
        "sanaap_backend_challenge_api.documents.management.commands.purge_deleted_files.get_minio_client"
    )
    def test_versioned_bucket_is_rejected(self, get_client):
        for status in ("Enabled", "Suspended"):
            get_client.return_value.get_bucket_versioning.return_value.status = status
            with self.assertRaises(CommandError):
                call_command("purge_deleted_files", stdout=StringIO())
        get_client.return_value.remove_object.assert_not_called()

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_expired_uploads_and_replacements_cannot_complete(self, get_client):
        old = timezone.now() - timedelta(
            seconds=settings.FILE_UPLOAD_COMPLETION_TTL + 1
        )
        replacement = FileReplacement.objects.create(
            file=self.document,
            original_name="new",
            size_bytes=4,
            previous_storage_key=self.document.storage_key,
        )
        FileReplacement.objects.filter(pk=replacement.pk).update(created_at=old)
        response = self.client.post(
            reverse("file-complete-replacement", args=[self.document.pk]),
            {"replacement_id": str(replacement.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        File.objects.filter(pk=self.document.pk).update(
            created_at=old, status=File.Status.PENDING
        )
        response = self.client.post(reverse("file-complete", args=[self.document.pk]))
        self.assertEqual(response.status_code, 400)
        get_client.assert_not_called()


class UploadLifecycleTests(APITestCase):
    @patch(
        "sanaap_backend_challenge_api.documents.management.commands.init_minio.get_minio_client"
    )
    def test_setup_preserves_other_rules_and_replaces_owned_rule(self, get_client):
        client = get_client.return_value
        client.get_bucket_policy.side_effect = S3Error(
            response=None,
            code="NoSuchBucketPolicy",
            message="missing",
            resource="resource",
            request_id="request",
            host_id="host",
        )
        client.get_bucket_versioning.return_value.status = None
        other = Rule(
            ENABLED,
            rule_id="other",
            rule_filter=Filter(prefix="other/"),
            expiration=Expiration(days=50),
        )
        old = Rule(
            ENABLED,
            rule_id="sanaap-staging-uploads",
            rule_filter=Filter(prefix="uploads/"),
            expiration=Expiration(days=90),
        )
        client.get_bucket_lifecycle.return_value = LifecycleConfig([other, old])
        call_command("init_minio", configure_upload_lifecycle=True, stdout=StringIO())
        rules = client.set_bucket_lifecycle.call_args.args[1].rules
        self.assertEqual(len(rules), 2)
        self.assertIs(rules[0], other)
        self.assertEqual(rules[1].rule_filter.prefix, "uploads/")
        self.assertEqual(
            rules[1].expiration.days, settings.MINIO_STAGING_EXPIRATION_DAYS
        )

    @patch(
        "sanaap_backend_challenge_api.documents.management.commands.init_minio.get_minio_client"
    )
    def test_setup_creates_rule_when_no_lifecycle_exists(self, get_client):
        client = get_client.return_value
        client.get_bucket_policy.side_effect = S3Error(
            response=None,
            code="NoSuchBucketPolicy",
            message="missing",
            resource="resource",
            request_id="request",
            host_id="host",
        )
        client.get_bucket_versioning.return_value.status = None
        client.get_bucket_lifecycle.return_value = None

        call_command("init_minio", configure_upload_lifecycle=True, stdout=StringIO())

        client.set_bucket_lifecycle.assert_called_once()
        bucket, lifecycle = client.set_bucket_lifecycle.call_args.args
        self.assertEqual(bucket, settings.MINIO_BUCKET)
        self.assertEqual(len(lifecycle.rules), 1)
        rule = lifecycle.rules[0]
        self.assertEqual(rule.rule_id, "sanaap-staging-uploads")
        self.assertEqual(rule.rule_filter.prefix, "uploads/")
        self.assertEqual(rule.expiration.days, settings.MINIO_STAGING_EXPIRATION_DAYS)
