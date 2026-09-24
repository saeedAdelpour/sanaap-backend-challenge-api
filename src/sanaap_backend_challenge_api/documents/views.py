from rest_framework.permissions import DjangoModelPermissions
from rest_framework.viewsets import ReadOnlyModelViewSet

from sanaap_backend_challenge_api.documents.models import File
from sanaap_backend_challenge_api.documents.serializers import FileSerializer


class FilePermissions(DjangoModelPermissions):
    perms_map = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": ["%(app_label)s.view_%(model_name)s"],
    }


class FileViewSet(ReadOnlyModelViewSet):
    """Metadata only. Upload, download, and deletion workflows come later."""

    serializer_class = FileSerializer
    permission_classes = [FilePermissions]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return File.objects.none()
        if user.is_superuser:
            return File.objects.all()
        return File.objects.filter(uploaded_by=user)
