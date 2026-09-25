from django.contrib import admin

from sanaap_backend_challenge_api.documents.models import File, FileReplacement


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "uploaded_by",
        "size_bytes",
        "created_at",
        "deleted_at",
        "deleted_by",
        "purged_at",
    )
    list_filter = ("status", "content_type")
    search_fields = ("title", "original_name")
    list_select_related = ("uploaded_by", "deleted_by")
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
        "deleted_at",
        "deleted_by",
        "purged_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FileReplacement)
class FileReplacementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "file",
        "original_name",
        "size_bytes",
        "created_at",
        "completed_at",
    )
    list_filter = ("created_at", "completed_at")
    search_fields = ("original_name", "file__title", "file__original_name")
    list_select_related = ("file",)
    readonly_fields = (
        "id",
        "file",
        "original_name",
        "size_bytes",
        "storage_key",
        "previous_storage_key",
        "created_at",
        "completed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
