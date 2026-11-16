import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("config", "0002_operix_roles"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountRetirement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("retired_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,
                                              related_name="operix_retirement", to=settings.AUTH_USER_MODEL)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                            related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
