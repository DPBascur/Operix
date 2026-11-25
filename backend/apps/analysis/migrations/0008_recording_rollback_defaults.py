from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analysis", "0007_recording_configuration")]

    operations = [
        migrations.AlterField("camerarevision", "source_sha256",
                              models.CharField(blank=True, default="", db_default="", max_length=64)),
        migrations.AlterField("camerarevision", "demonstration",
                              models.BooleanField(default=False, db_default=False)),
    ]
