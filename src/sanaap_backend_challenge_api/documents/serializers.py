from rest_framework import serializers

from sanaap_backend_challenge_api.documents.models import File


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = [
            "id",
            "title",
            "original_name",
            "content_type",
            "size_bytes",
            "uploaded_by",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
