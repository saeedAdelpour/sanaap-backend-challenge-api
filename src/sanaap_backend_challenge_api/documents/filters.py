from django_filters import rest_framework as filters

from sanaap_backend_challenge_api.documents.models import File


class FileFilter(filters.FilterSet):
    title = filters.CharFilter(lookup_expr="icontains")
    original_name = filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = File
        fields = ["title", "original_name", "status"]
