from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from minio.error import S3Error
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from urllib3.exceptions import HTTPError

from sanaap_backend_challenge_api.documents.models import File, FileReplacement


class FileAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="api-user")
        self.user.groups.add(Group.objects.get(name="Editor"))
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.document = File.objects.create(
            title="Policy",
            original_name="policy.pdf",
            storage_key="uploads/test-key",
            content_type="application/octet-stream",
            size_bytes=4,
        )

    def test_authenticated_metadata_and_no_delete(self):
        response = self.client.get(reverse("file-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("storage_key", response.data["results"][0])
        url = reverse("file-detail", args=[self.document.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(self.client.patch(url, {}, format="json").status_code, 200)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_authenticated_upload_returns_put_url_without_proxying_bytes(
        self, get_client
    ):
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
        self.assertEqual(document.uploaded_by, self.user)
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


class FileModificationTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="api-user")
        self.user.groups.add(Group.objects.get(name="Editor"))
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.document = File.objects.create(
            title="Original",
            original_name="old.pdf",
            size_bytes=4,
            content_type="application/octet-stream",
            storage_key="documents/old",
            status=File.Status.READY,
        )

    def replacement(self, **kwargs):
        return FileReplacement.objects.create(
            file=self.document,
            original_name="new.pdf",
            size_bytes=8,
            previous_storage_key=self.document.storage_key,
            **kwargs,
        )

    def complete(self, replacement):
        return self.client.post(
            reverse("file-complete-replacement", args=[self.document.pk]),
            {"replacement_id": str(replacement.pk)},
            format="json",
        )

    def test_patch_changes_only_metadata(self):
        response = self.client.patch(
            reverse("file-detail", args=[self.document.pk]),
            {
                "title": "Renamed",
                "original_name": "renamed.pdf",
                "storage_key": "bad",
                "size_bytes": 999,
                "status": "failed",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.title, "Renamed")
        self.assertEqual(self.document.original_name, "renamed.pdf")
        self.assertEqual(self.document.storage_key, "documents/old")
        self.assertEqual(self.document.size_bytes, 4)
        self.assertEqual(self.document.status, File.Status.READY)

    def test_blank_metadata_is_rejected(self):
        response = self.client.patch(
            reverse("file-detail", args=[self.document.pk]),
            {"title": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_initiation_leaves_current_file_unchanged(self, get_client):
        get_client.return_value.presigned_put_object.return_value = (
            "https://storage/put"
        )
        response = self.client.post(
            reverse("file-replace", args=[self.document.pk]),
            {"original_name": "new.pdf", "size_bytes": 8},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.document.refresh_from_db()
        self.assertEqual(self.document.storage_key, "documents/old")
        self.assertEqual(self.document.status, File.Status.READY)
        self.assertEqual(FileReplacement.objects.count(), 1)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_signing_failure_leaves_no_replacement(self, get_client):
        get_client.return_value.presigned_put_object.side_effect = HTTPError("offline")
        response = self.client.post(
            reverse("file-replace", args=[self.document.pk]),
            {"original_name": "new.pdf", "size_bytes": 8},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(FileReplacement.objects.exists())

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_completed_replacement_and_repeat(self, get_client):
        replacement = self.replacement()
        client = get_client.return_value
        client.stat_object.return_value.size = 8
        client.stat_object.return_value.etag = "new-etag"
        response = self.complete(replacement)
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.size_bytes, 8)
        self.assertEqual(self.document.original_name, "new.pdf")
        self.assertEqual(self.document.title, "Original")
        self.assertIn(replacement.pk.hex, self.document.storage_key)
        self.assertEqual(self.complete(replacement).status_code, 200)
        client.copy_object.assert_called_once()

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_bad_size_and_storage_failure_preserve_current_file(self, get_client):
        replacement = self.replacement()
        client = get_client.return_value
        client.stat_object.return_value.size = 9
        self.assertEqual(self.complete(replacement).status_code, 400)
        client.stat_object.return_value.size = 8
        client.stat_object.return_value.etag = "new-etag"
        client.copy_object.side_effect = HTTPError("offline")
        self.assertEqual(self.complete(replacement).status_code, 503)
        self.document.refresh_from_db()
        replacement.refresh_from_db()
        self.assertEqual(self.document.storage_key, "documents/old")
        self.assertIsNone(replacement.completed_at)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_competing_replacement_is_rejected(self, get_client):
        first = self.replacement()
        second = self.replacement()
        client = get_client.return_value
        client.stat_object.return_value.size = 8
        client.stat_object.return_value.etag = "etag"
        self.assertEqual(self.complete(first).status_code, 200)
        self.assertEqual(self.complete(second).status_code, 409)
        client.copy_object.assert_called_once()

    def test_replacement_cannot_be_completed_for_different_file(self):
        replacement = self.replacement()
        other = File.objects.create(
            title="Other",
            original_name="other.pdf",
            size_bytes=4,
            content_type="application/octet-stream",
            storage_key="documents/other",
            status=File.Status.READY,
        )
        response = self.client.post(
            reverse("file-complete-replacement", args=[other.pk]),
            {"replacement_id": str(replacement.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 404)


class TokenAuthenticationTests(APITestCase):
    def setUp(self):
        self.password = uuid4().hex
        self.user = get_user_model().objects.create_user(
            username="login-user", password=self.password
        )

    def test_login_token_authenticates_file_api(self):
        self.user.groups.add(Group.objects.get(name="Viewer"))
        response = self.client.post(
            reverse("api-login"),
            {"username": self.user.username, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        self.assertEqual(self.client.get(reverse("file-list")).status_code, 200)

    def test_invalid_login_does_not_issue_token(self):
        response = self.client.post(
            reverse("api-login"),
            {"username": self.user.username, "password": uuid4().hex},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Token.objects.exists())

    def test_all_file_actions_require_token(self):
        file_id = uuid4()
        endpoints = [
            ("get", reverse("file-list")),
            ("post", reverse("file-list")),
            ("get", reverse("file-detail", args=[file_id])),
            ("patch", reverse("file-detail", args=[file_id])),
            ("get", reverse("file-download", args=[file_id])),
            ("post", reverse("file-complete", args=[file_id])),
            ("post", reverse("file-replace", args=[file_id])),
            ("post", reverse("file-complete-replacement", args=[file_id])),
        ]
        for method, url in endpoints:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 401)

    def test_invalid_and_inactive_tokens_are_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {uuid4().hex}")
        self.assertEqual(self.client.get(reverse("file-list")).status_code, 401)
        token = Token.objects.create(user=self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(self.client.get(reverse("file-list")).status_code, 401)

    def test_session_cookie_alone_does_not_authenticate_file_api(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("file-list")).status_code, 401)


class FileGroupPermissionTests(APITestCase):
    def test_group_permissions_are_inherited(self):
        expected = {
            "Admin": {
                "upload_file",
                "replace_file",
                "download_file",
                "destroy_file",
                "change_file",
                "view_file",
            },
            "Editor": {
                "upload_file",
                "replace_file",
                "download_file",
                "change_file",
                "view_file",
            },
            "Viewer": {"download_file", "view_file"},
        }
        for role, codenames in expected.items():
            with self.subTest(role=role):
                user = get_user_model().objects.create_user(username=role)
                user.groups.add(Group.objects.get(name=role))
                self.assertEqual(
                    user.get_all_permissions(),
                    {f"documents.{codename}" for codename in codenames},
                )
                self.assertFalse(user.user_permissions.exists())

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_create_checks_inherited_upload_permission(self, get_client):
        get_client.return_value.presigned_put_object.return_value = (
            "https://storage/put"
        )
        for role, expected_status in (
            ("Admin", 201),
            ("Editor", 201),
            ("Viewer", 403),
            (None, 403),
        ):
            with self.subTest(role=role):
                user = get_user_model().objects.create_user(username=role or "no-group")
                if role:
                    user.groups.add(Group.objects.get(name=role))
                token = Token.objects.create(user=user)
                self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
                get_client.reset_mock()
                count = File.objects.count()
                response = self.client.post(
                    reverse("file-list"),
                    {"original_name": "test.pdf", "size_bytes": 4},
                    format="json",
                )
                self.assertEqual(response.status_code, expected_status)
                if expected_status == 403:
                    get_client.assert_not_called()
                    self.assertEqual(File.objects.count(), count)

    @patch("sanaap_backend_challenge_api.documents.services.get_minio_client")
    def test_groups_control_all_remaining_file_actions(self, get_client):
        document = File.objects.create(
            title="Policy",
            original_name="policy.pdf",
            storage_key="documents/policy",
            content_type="application/pdf",
            size_bytes=4,
            status=File.Status.READY,
        )
        get_client.return_value.presigned_get_object.return_value = (
            "https://storage/get"
        )
        for role in ("Admin", "Editor", "Viewer", None):
            user = get_user_model().objects.create_user(username=role or "no-group")
            if role:
                user.groups.add(Group.objects.get(name=role))
            token = Token.objects.create(user=user)
            self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
            can_read = role is not None
            can_write = role in ("Admin", "Editor")
            endpoints = [
                ("get", "file-list", [], 200 if can_read else 403),
                ("head", "file-list", [], 200 if can_read else 403),
                ("options", "file-list", [], 200 if can_read else 403),
                ("get", "file-detail", [document.pk], 200 if can_read else 403),
                ("get", "file-download", [document.pk], 200 if can_read else 403),
                ("patch", "file-detail", [document.pk], 200 if can_write else 403),
                ("post", "file-complete", [document.pk], 200 if can_write else 403),
                ("post", "file-replace", [document.pk], 400 if can_write else 403),
                (
                    "post",
                    "file-complete-replacement",
                    [document.pk],
                    400 if can_write else 403,
                ),
            ]
            for method, name, args, expected in endpoints:
                with self.subTest(role=role, method=method, endpoint=name):
                    response = getattr(self.client, method)(reverse(name, args=args))
                    self.assertEqual(response.status_code, expected)

    def test_view_permission_does_not_grant_download_or_write_access(self):
        user = get_user_model().objects.create_user(username="metadata-only")
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="documents", codename="view_file"
            )
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(self.client.get(reverse("file-list")).status_code, 200)
        for method, name in (
            ("get", "file-download"),
            ("patch", "file-detail"),
            ("post", "file-complete"),
            ("post", "file-replace"),
            ("post", "file-complete-replacement"),
        ):
            with self.subTest(endpoint=name):
                response = getattr(self.client, method)(reverse(name, args=[uuid4()]))
                self.assertEqual(response.status_code, 403)
