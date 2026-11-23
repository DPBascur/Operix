from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analysis", "0005_cameralabcontrol_camerarun_managed")]

    operations = [
        migrations.AddField(model_name="cameralabcontrol", name="playlists", field=models.JSONField(default=dict)),
        migrations.AddField(model_name="cameralabcontrol", name="playback", field=models.JSONField(default=dict)),
        migrations.AddField(model_name="camerarun", name="playback", field=models.JSONField(default=dict)),
        migrations.AddField(model_name="camerarevision", name="capture_signature",
                            field=models.CharField(blank=True, max_length=64)),
    ]
