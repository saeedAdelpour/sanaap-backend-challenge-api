from django.contrib import admin

from sanaap_backend_challenge_api.documents.models import File


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "uploaded_by", "size_bytes", "created_at")
    list_filter = ("status", "content_type")
    search_fields = ("title", "original_name")
    list_select_related = ("uploaded_by",)
    readonly_fields = (
        "id",
        "title",
        "original_name",
        "storage_key",
        "content_type",
        "size_bytes",
        "uploaded_by",
        "status",
        "created_at",
        "updated_at",
    )
