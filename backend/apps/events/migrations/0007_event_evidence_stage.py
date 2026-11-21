from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0006_remove_event_unique_event_per_analysis_candidate_and_more")]

    operations = [
        migrations.AddField(
            model_name="event",
            name="evidence_stage",
            field=models.CharField(
                blank=True, choices=[("pending", "Pending"), ("finished", "Finished")],
                default="", max_length=8,
            ),
        ),
    ]
