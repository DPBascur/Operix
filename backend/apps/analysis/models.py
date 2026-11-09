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
