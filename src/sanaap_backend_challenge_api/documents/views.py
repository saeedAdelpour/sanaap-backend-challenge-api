from django.conf import settings
from rest_framework import mixins, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from sanaap_backend_challenge_api.documents.models import File
from sanaap_backend_challenge_api.documents.permissions import FilePermission
from sanaap_backend_challenge_api.documents.serializers import (
    FileReplacementCompleteSerializer,
    FileReplacementSerializer,
    FileSerializer,
    FileUpdateSerializer,
    FileUploadSerializer,
)
from sanaap_backend_challenge_api.documents.services import (
    complete_replacement,
    complete_upload,
    get_download_url,
    initiate_replacement,
    initiate_upload,
    update_file_metadata,
)


class FileViewSet(mixins.CreateModelMixin, ReadOnlyModelViewSet):
    """Token-authenticated metadata and presigned uploads. Deletion is not implemented."""

    serializer_class = FileSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, FilePermission]

    def get_serializer_class(self):
        if self.action == "create":
            return FileUploadSerializer
        if self.action in {"update", "partial_update"}:
            return FileUpdateSerializer
        if self.action == "replace":
            return FileReplacementSerializer
        if self.action == "complete_replacement":
            return FileReplacementCompleteSerializer
        return FileSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document, upload_url = initiate_upload(
            **serializer.validated_data,
            uploaded_by=request.user,
        )
        return Response(
            {
                **FileSerializer(document).data,
                "upload_url": upload_url,
                "upload_method": "PUT",
                "expires_in": settings.MINIO_UPLOAD_URL_TTL,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, *args, **kwargs):
        document = complete_upload(self.get_object().pk)
        return Response(FileSerializer(document).data)

    def get_queryset(self):
        return File.objects.all()

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, *args, **kwargs):
        document, url = get_download_url(self.get_object().pk)

        return Response(
            {
                **FileSerializer(document).data,
                "download_url": url,
                "expires_in": settings.MINIO_UPLOAD_URL_TTL,
            }
        )

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        document = update_file_metadata(
            self.get_object().pk, **serializer.validated_data
        )
        return Response(FileSerializer(document).data)

    @action(detail=True, methods=["post"], url_path="replace")
    def replace(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        replacement, url = initiate_replacement(
            self.get_object().pk, **serializer.validated_data
        )
        return Response(
            {
                "id": str(replacement.file_id),
                "replacement_id": str(replacement.pk),
                "upload_url": url,
                "upload_method": "PUT",
                "expires_in": settings.MINIO_UPLOAD_URL_TTL,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="replace/complete")
    def complete_replacement(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = complete_replacement(
            self.get_object().pk, **serializer.validated_data
        )
        return Response(FileSerializer(document).data)
