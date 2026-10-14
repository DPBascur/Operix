from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0002_event_evidence_image")]

    operations = [
        migrations.AddConstraint(
            model_name="event",
            constraint=models.UniqueConstraint(
                fields=(
                    "analysis_run_id", "view_id", "frame_index", "rule_id",
                    "rule_version", "track_id", "zone_id",
                ),
                name="unique_event_per_analysis_candidate",
            ),
        ),
    ]
