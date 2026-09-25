import uuid

from django.conf import settings
from django.db import models


class File(models.Model):
    """Metadata for a private object; storage operations belong in services."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    storage_key = models.CharField(
        max_length=1024,
        unique=True,
        help_text="Private object key, never a public or presigned URL.",
    )
    content_type = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_files",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="deleted_files",
        null=True,
        blank=True,
    )
    purged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        permissions = [
            ("upload_file", "Can upload files"),
            ("replace_file", "Can replace files"),
            ("download_file", "Can download files"),
            ("destroy_file", "Can destroy files"),
        ]

    def __str__(self):
        return self.title


class FileReplacement(models.Model):
    """A pending replacement; the current document remains downloadable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        File, on_delete=models.CASCADE, related_name="replacements"
    )
    original_name = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    previous_storage_key = models.CharField(max_length=1024)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def storage_key(self):
        return f"uploads/{self.id.hex}"
