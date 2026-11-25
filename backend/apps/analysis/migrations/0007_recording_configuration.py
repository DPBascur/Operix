from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analysis", "0006_lab_playlists")]

    operations = [
        migrations.AddField("camerarevision", "source_sha256", models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField("camerarevision", "demonstration", models.BooleanField(default=False)),
        migrations.AddIndex("camerarevision", models.Index(
            fields=["camera_id", "capture_signature", "-revision"], name="camera_capture_revision_idx")),
    ]
