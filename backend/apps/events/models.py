import uuid

from django.db import models


def event_evidence_path(instance, filename):
    return f"events/{instance.pk}/{uuid.uuid4().hex}.png"


class Event(models.Model):
    """Persisted technical event, distinct from an in-memory EventCandidate."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis_run_id = models.UUIDField()
    view_id = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(db_index=True)
    video_timestamp_s = models.DecimalField(max_digits=12, decimal_places=3)
    frame_index = models.PositiveIntegerField()
    event_type = models.CharField(max_length=64, db_index=True)
    rule_id = models.CharField(max_length=64)
    rule_version = models.PositiveIntegerField()
    rule_parameters = models.JSONField()
    zone_id = models.CharField(max_length=64)
    track_id = models.PositiveIntegerField()
    class_name = models.CharField(max_length=64)
    observed_inside = models.BooleanField()
    observed_dwell_time_s = models.DecimalField(max_digits=12, decimal_places=3)
    evidence_image = models.FileField(upload_to=event_evidence_path, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at", "-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.rule_id} v{self.rule_version} · {self.id}"
