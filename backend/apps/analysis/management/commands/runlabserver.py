"""Use the existing single-process Django server and its camera workers."""
from django.contrib.staticfiles.management.commands.runserver import Command as RunServer

from apps.analysis.lab_control import start_reconciler


class Command(RunServer):
    def inner_run(self, *args, **options):
        start_reconciler()
        return super().inner_run(*args, **options)
