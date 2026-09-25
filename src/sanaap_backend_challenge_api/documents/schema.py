"""OpenAPI response contracts and annotations for document operations."""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers

from sanaap_backend_challenge_api.documents.models import File
from sanaap_backend_challenge_api.documents.serializers import FileSerializer

FILE_STATUS_CHOICES = File.Status.choices


class FileUploadResponseSerializer(FileSerializer):
    upload_url = serializers.URLField()
    upload_method = serializers.ChoiceField(choices=["PUT"])
    expires_in = serializers.IntegerField()

    class Meta(FileSerializer.Meta):
        fields = [
            *FileSerializer.Meta.fields,
            "upload_url",
            "upload_method",
            "expires_in",
        ]


class FileDownloadResponseSerializer(FileSerializer):
    download_url = serializers.URLField()
    expires_in = serializers.IntegerField()

    class Meta(FileSerializer.Meta):
        fields = [*FileSerializer.Meta.fields, "download_url", "expires_in"]


class FileReplacementResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    replacement_id = serializers.UUIDField()
    upload_url = serializers.URLField()
    upload_method = serializers.ChoiceField(choices=["PUT"])
    expires_in = serializers.IntegerField()


file_schema = extend_schema_view(
    list=extend_schema(summary="List active files"),
    retrieve=extend_schema(summary="Get file metadata"),
    create=extend_schema(
        summary="Start an upload",
        description="Upload raw bytes with PUT to upload_url, then call complete.",
        responses={201: FileUploadResponseSerializer},
    ),
    partial_update=extend_schema(
        summary="Update file metadata", responses=FileSerializer
    ),
    destroy=extend_schema(
        summary="Soft delete a file",
        description="Requires the destroy_file permission (Admin group).",
        responses={204: None},
    ),
    complete=extend_schema(
        summary="Verify and finalize an upload", request=None, responses=FileSerializer
    ),
    download=extend_schema(
        summary="Get a temporary download URL",
        responses=FileDownloadResponseSerializer,
        filters=False,
    ),
    replace=extend_schema(
        summary="Start a content replacement",
        description="PUT bytes to upload_url, then call replace/complete with replacement_id.",
        responses={201: FileReplacementResponseSerializer},
    ),
    complete_replacement=extend_schema(
        summary="Verify and finalize a replacement", responses=FileSerializer
    ),
)
