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


class FileUploadSerializer(serializers.Serializer):
    original_name = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=1, max_value=5 * 1024**3)
    title = serializers.CharField(max_length=255, required=False)


class FileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ["title", "original_name"]


class FileReplacementSerializer(serializers.Serializer):
    original_name = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField(min_value=1, max_value=5 * 1024**3)


class FileReplacementCompleteSerializer(serializers.Serializer):
    replacement_id = serializers.UUIDField()
