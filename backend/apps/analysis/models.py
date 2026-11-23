import uuid

from django.conf import settings
from django.db import models


class SpatialConfiguration(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    source_sha256 = models.CharField(max_length=64)
    revision = models.PositiveIntegerField()
    document = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("owner", "source_sha256", "revision"),
                                                name="unique_spatial_source_revision")]


class AnalysisSource(models.Model):
    """Identity and metadata of an opened source. Video storage remains temporary."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    source_sha256 = models.CharField(max_length=64)
    filename = models.CharField(max_length=120)
    profile = models.CharField(max_length=1)
    source_kind = models.CharField(max_length=6)
    demo_source_id = models.CharField(max_length=64, null=True)
    source_bytes = models.PositiveBigIntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("owner", "source_sha256"), name="unique_analysis_source")
        ]


class RuleCatalogEntry(models.Model):
    class Kind(models.TextChoices):
        TEMPLATE = "template"
        SET = "set"
        ASSIGNMENT = "assignment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    version = models.PositiveIntegerField(default=1)
    document = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=("owner", "kind"))]


class RuleCatalogRevision(models.Model):
    entry = models.ForeignKey(RuleCatalogEntry, related_name="history", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    document = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entry", "version"), name="unique_rule_catalog_revision")
        ]


class AnalysisRunSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    source_sha256 = models.CharField(max_length=64)
    profile = models.CharField(max_length=1)
    spatial_revision = models.PositiveIntegerField(null=True)
    configuration = models.JSONField()
    config_sha256 = models.CharField(max_length=64)
    policy = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CameraRevision(models.Model):
    camera_id = models.CharField(max_length=64)
    revision = models.PositiveIntegerField()
    document = models.JSONField()
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("camera_id", "revision"),
                                                name="unique_lab_camera_revision")]


class CameraRun(models.Model):
    snapshot = models.OneToOneField(AnalysisRunSnapshot, primary_key=True, on_delete=models.PROTECT)
    camera_id = models.CharField(max_length=64, db_index=True)
    active = models.BooleanField(default=True)
    terminal_state = models.CharField(max_length=16, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True)
    metrics = models.JSONField(default=dict)
    provenance = models.JSONField(default=dict)
    managed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("camera_id",), condition=models.Q(active=True),
                                                name="unique_active_lab_camera")]


class CameraLabControl(models.Model):
    enabled = models.BooleanField(default=False)
    cameras = models.JSONField(default=dict)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)
