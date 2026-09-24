from django.conf import settings
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from sanaap_backend_challenge_api.documents.models import File
from sanaap_backend_challenge_api.documents.serializers import (
    FileSerializer,
    FileUploadSerializer,
)
from sanaap_backend_challenge_api.documents.services import (
    complete_upload,
    initiate_upload,
)


class FileViewSet(mixins.CreateModelMixin, ReadOnlyModelViewSet):
    """Public metadata and presigned uploads. Deletion is not implemented."""

    serializer_class = FileSerializer
    authentication_classes = []
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action == "create":
            return FileUploadSerializer
        return FileSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document, upload_url = initiate_upload(**serializer.validated_data)
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
