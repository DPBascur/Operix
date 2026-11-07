from django.db import models


class LoginBucket(models.Model):
    key = models.CharField(max_length=80, primary_key=True)
    window = models.BigIntegerField()
    attempts = models.PositiveIntegerField()
