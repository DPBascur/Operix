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
    track_id = models.PositiveIntegerField(null=True)
    class_name = models.CharField(max_length=64, blank=True)
    observed_inside = models.BooleanField(null=True)
    observed_dwell_time_s = models.DecimalField(max_digits=18, decimal_places=9, null=True)
    # Vacíos para registros históricos: no se reconstruyen observaciones inexistentes.
    interaction = models.JSONField(default=dict, blank=True)
    observations = models.JSONField(default=dict, blank=True)
    episode = models.JSONField(default=dict, blank=True)
    source = models.JSONField(default=dict, blank=True)
    pair_key = models.CharField(max_length=64, null=True, editable=False)
    evidence_image = models.FileField(upload_to=event_evidence_path, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at", "-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "analysis_run_id", "view_id", "frame_index", "rule_id",
                    "rule_version", "track_id", "class_name", "zone_id",
                ),
                name="unique_event_per_analysis_candidate",
                condition=models.Q(event_type="zone_dwell"),
            ),
            models.UniqueConstraint(
                fields=("analysis_run_id", "view_id", "frame_index", "rule_id",
                        "rule_version", "pair_key", "zone_id"),
                name="unique_pair_per_analysis_candidate",
                condition=models.Q(event_type="person_forklift_proximity"),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rule_id} v{self.rule_version} · {self.id}"
