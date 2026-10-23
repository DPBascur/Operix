from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0003_event_candidate_identity")]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="observed_dwell_time_s",
            field=models.DecimalField(max_digits=18, decimal_places=9),
        ),
    ]
