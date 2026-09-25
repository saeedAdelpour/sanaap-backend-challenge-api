from django.db import migrations


def create_file_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    alias = schema_editor.connection.alias

    # Permissions normally appear in post_migrate, after this migration runs.
    content_type, _ = ContentType.objects.using(alias).get_or_create(
        app_label="documents", model="file"
    )
    permission_names = {
        "upload_file": "Can upload files",
        "replace_file": "Can replace files",
        "download_file": "Can download files",
        "destroy_file": "Can destroy files",
        "change_file": "Can change file",
        "view_file": "Can view file",
    }
    permissions = {}
    for codename, name in permission_names.items():
        permissions[codename], _ = Permission.objects.using(alias).get_or_create(
            content_type=content_type, codename=codename, defaults={"name": name}
        )

    roles = {
        "Admin": tuple(permission_names),
        "Editor": (
            "upload_file",
            "replace_file",
            "download_file",
            "change_file",
            "view_file",
        ),
        "Viewer": ("download_file", "view_file"),
    }
    for name, codenames in roles.items():
        group, _ = Group.objects.using(alias).get_or_create(name=name)
        group.permissions.add(*(permissions[codename] for codename in codenames))


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0004_alter_file_options"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    # Preserve memberships and existing groups if this migration is rolled back.
    operations = [migrations.RunPython(create_file_groups, migrations.RunPython.noop)]
