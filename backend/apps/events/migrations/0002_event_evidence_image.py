from django.db import migrations, models

import apps.events.models


class Migration(migrations.Migration):
    dependencies = [("events", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="event",
            name="evidence_image",
            field=models.FileField(blank=True, null=True, upload_to=apps.events.models.event_evidence_path),
        ),
    ]
