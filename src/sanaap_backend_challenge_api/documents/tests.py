from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APITestCase

from sanaap_backend_challenge_api.documents.models import File


class FileAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(username="owner")
        cls.other = user_model.objects.create_user(username="other")
        cls.admin = user_model.objects.create_user(
            username="admin", is_staff=True, is_superuser=True
        )
        permission = Permission.objects.get(
            content_type__app_label="documents", codename="view_file"
        )
        cls.owner.user_permissions.add(permission)
        cls.other.user_permissions.add(permission)
        cls.file = File.objects.create(
            title="Insurance policy",
            original_name="policy.pdf",
            storage_key="private/unique-policy.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            uploaded_by=cls.owner,
        )

    def test_authentication_and_view_permission_are_required(self):
        url = reverse("file-list")
        self.assertEqual(self.client.get(url).status_code, 403)
        user = get_user_model().objects.create_user(username="no-permission")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_owner_sees_metadata_without_storage_key(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("file-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("storage_key", response.data["results"][0])
        self.assertEqual(self.file.status, File.Status.PENDING)

    def test_other_user_cannot_list_or_retrieve_file(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(reverse("file-list")).data["count"], 0)
        response = self.client.get(reverse("file-detail", args=[self.file.pk]))
        self.assertEqual(response.status_code, 404)

    def test_superuser_can_read_but_write_routes_are_not_available(self):
        self.client.force_authenticate(self.admin)
        url = reverse("file-detail", args=[self.file.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(self.client.patch(url, {"title": "Changed"}).status_code, 405)
        self.assertEqual(self.client.post(reverse("file-list"), {}).status_code, 405)
