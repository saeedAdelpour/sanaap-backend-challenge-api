from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.urls import reverse
from minio.error import S3Error
from rest_framework.test import APITestCase
from urllib3.exceptions import HTTPError

from sanaap_backend_challenge_api.documents.models import File


class FileAPITests(APITestCase):
    def setUp(self):
        self.document = File.objects.create(
            title="Policy",
            original_name="policy.pdf",
            storage_key="uploads/test-key",
            content_type="application/octet-stream",
            size_bytes=4,
        )

    def test_public_metadata_and_no_delete(self):
        response = self.client.get(reverse("file-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("storage_key", response.data["results"][0])
        url = reverse("file-detail", args=[self.document.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(self.client.patch(url, {}, format="json").status_code, 405)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_anonymous_upload_returns_put_url_without_proxying_bytes(self, get_client):
        get_client.return_value.presigned_put_object.return_value = (
            "https://storage/upload"
        )
        response = self.client.post(
            reverse("file-list"),
            {"original_name": "new.pdf", "size_bytes": 4, "uploaded_by": 999},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        document = File.objects.get(pk=response.data["id"])
        self.assertIsNone(document.uploaded_by)
        self.assertEqual(document.status, File.Status.PENDING)
        self.assertEqual(response.data["upload_method"], "PUT")
        self.assertEqual(response.data["upload_url"], "https://storage/upload")
        get_client.return_value.presigned_put_object.assert_called_once_with(
            settings.MINIO_BUCKET,
            document.storage_key,
            expires=timedelta(seconds=settings.MINIO_UPLOAD_URL_TTL),
        )
        get_client.return_value.put_object.assert_not_called()

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_bad_metadata_is_rejected_before_signing(self, get_client):
        for data in (
            {},
            {"original_name": "x", "size_bytes": 0},
            {"original_name": "x", "size_bytes": -1},
        ):
            response = self.client.post(reverse("file-list"), data, format="json")
            self.assertEqual(response.status_code, 400)
        get_client.assert_not_called()

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_signing_failure_does_not_create_record(self, get_client):
        get_client.return_value.presigned_put_object.side_effect = HTTPError("offline")
        response = self.client.post(
            reverse("file-list"), {"original_name": "x", "size_bytes": 4}, format="json"
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(File.objects.count(), 1)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_completion_publishes_separate_key_and_is_idempotent(self, get_client):
        client = get_client.return_value
        client.stat_object.return_value.size = 4
        client.stat_object.return_value.etag = "abc"
        url = reverse("file-complete", args=[self.document.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, File.Status.READY)
        self.assertEqual(self.document.storage_key, f"documents/{self.document.pk.hex}")
        client.copy_object.assert_called_once()
        self.assertEqual(self.client.post(url).status_code, 200)
        client.copy_object.assert_called_once()

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_size_mismatch_stays_pending(self, get_client):
        get_client.return_value.stat_object.return_value.size = 9
        response = self.client.post(reverse("file-complete", args=[self.document.pk]))
        self.assertEqual(response.status_code, 400)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, File.Status.PENDING)
        get_client.return_value.copy_object.assert_not_called()

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_missing_object_cannot_be_completed(self, get_client):
        get_client.return_value.stat_object.side_effect = S3Error(
            response=None,
            code="NoSuchKey",
            message="Missing",
            resource="resource",
            request_id="request",
            host_id="host",
        )
        response = self.client.post(reverse("file-complete", args=[self.document.pk]))
        self.assertEqual(response.status_code, 400)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, File.Status.PENDING)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_copy_failure_can_be_retried(self, get_client):
        client = get_client.return_value
        client.stat_object.return_value.size = 4
        client.stat_object.return_value.etag = "abc"
        client.copy_object.side_effect = HTTPError("offline")
        response = self.client.post(reverse("file-complete", args=[self.document.pk]))
        self.assertEqual(response.status_code, 503)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, File.Status.PENDING)
        self.assertEqual(self.document.storage_key, "uploads/test-key")
