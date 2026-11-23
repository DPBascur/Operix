from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0004_camerarun_provenance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="camerarun",
            name="managed",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="CameraLabControl",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False)),
                ("cameras", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
