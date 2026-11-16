from django.db import migrations


def create_groups(apps, schema_editor):
    groups = apps.get_model("auth", "Group").objects.using(schema_editor.connection.alias)
    for name in ("Administrador Operix", "Visualizador"):
        groups.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("config", "0001_loginbucket"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(create_groups, migrations.RunPython.noop)]
