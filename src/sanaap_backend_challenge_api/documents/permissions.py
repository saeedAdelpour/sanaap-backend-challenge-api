from rest_framework.permissions import BasePermission


class FilePermission(BasePermission):
    """Check Django model permissions, including permissions inherited from groups."""

    message = "You do not have permission to perform this file action."
    action_permissions = {
        "list": "documents.view_file",
        "retrieve": "documents.view_file",
        "metadata": "documents.view_file",
        "create": "documents.upload_file",
        "complete": "documents.upload_file",
        "update": "documents.change_file",
        "partial_update": "documents.change_file",
        "replace": "documents.replace_file",
        "complete_replacement": "documents.replace_file",
        "download": "documents.download_file",
        "destroy": "documents.destroy_file",
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Let DRF return 405 for methods the view does not implement.
        if request.method not in view.allowed_methods:
            return True
        permission = self.action_permissions.get(view.action)
        return bool(permission and request.user.has_perm(permission))
