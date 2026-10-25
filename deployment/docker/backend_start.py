"""Startup del prototipo: una instancia Django con threads y su worker existente."""
import os
import subprocess
import sys
import time

import psycopg

for attempt in range(30):
    try:
        with psycopg.connect(dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
                             password=os.environ["POSTGRES_PASSWORD"], host=os.environ["POSTGRES_HOST"],
                             port=os.environ["POSTGRES_PORT"], connect_timeout=3):
            break
    except psycopg.OperationalError:
        if attempt == 29:
            raise RuntimeError("PostgreSQL no disponible; startup cancelado") from None
        time.sleep(1)
subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], check=True)
subprocess.run([sys.executable, "manage.py", "check"], check=True)
os.execv(sys.executable, [sys.executable, "manage.py", "runserver", "0.0.0.0:8000", "--noreload"])
