from django.conf import settings
from django.db import models


class LoginBucket(models.Model):
    key = models.CharField(max_length=80, primary_key=True)
    window = models.BigIntegerField()
    attempts = models.PositiveIntegerField()


class AccountRetirement(models.Model):
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="operix_retirement",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="+",
    )
    retired_at = models.DateTimeField(auto_now_add=True)
