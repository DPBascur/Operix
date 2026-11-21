from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analysis", "0003_rtsp_lab")]

    operations = [
        migrations.AddField(
            model_name="camerarun",
            name="provenance",
            field=models.JSONField(default=dict),
        ),
    ]
