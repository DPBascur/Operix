import hashlib
import json
import os
import subprocess
from copy import deepcopy

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.response import Response

from .models import SpatialConfiguration
from .sessions import ROOT, RESTARTABLE
from .views import AnalysisView


class SpatialConfigurationView(AnalysisView):
    def get(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None:
            return Response({"detail":"Sesión inexistente"}, status=404)
        saved = SpatialConfiguration.objects.filter(owner=request.user, source_sha256=session.source_sha256).order_by("-revision").first()
        return Response({"source_sha256":session.source_sha256, "document":session.operational_config(),
                         "revision":saved.revision if saved else 0,
                         "saved":saved.document if saved else None})

    def put(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None:
            return Response({"detail":"Sesión inexistente"}, status=404)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"document","revision"} or type(data["revision"]) is not int:
            return Response({"detail":"Indique documento y revisión"}, status=400)
        if len(json.dumps(data)) > 65536:
            return Response({"detail":"Configuración demasiado grande"}, status=400)
        with session._guard:
            if session.state not in RESTARTABLE or (session.process and session.process.poll() is None):
                return Response({"detail":"Detenga el análisis antes de editar"}, status=409)
            try:
                checked = subprocess.run([settings.OPERIX_ENGINE_PYTHON, "-B",
                    str(ROOT/"engine/scripts/validate_spatial_config.py"), session.source_sha256],
                    input=json.dumps(data["document"], allow_nan=False), capture_output=True, text=True,
                    encoding="utf8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=20)
                if checked.returncode:
                    return Response({"detail":checked.stderr.strip()[-400:] or "Configuración inválida"}, status=400)
                document = json.loads(checked.stdout)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return Response({"detail":"No se pudo validar con el Motor"}, status=400)
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                history = SpatialConfiguration.objects.filter(owner=request.user, source_sha256=session.source_sha256).order_by("-revision")
                saved = history.first()
                revision = saved.revision if saved else 0
                if revision != data["revision"]:
                    return Response({"detail":"La configuración cambió. Recupere la revisión actual."}, status=409)
                calibration = document.get("calibration")
                old_calibration = saved.document.get("calibration") if saved else None
                if calibration:
                    keys = ("image_points", "ground_points_m", "status", "zones_reviewed")
                    same = old_calibration and all(calibration[k] == old_calibration[k] for k in keys)
                    highest = max((v or 0 for v in history.values_list("document__calibration__version", flat=True)), default=0)
                    calibration["version"] = old_calibration["version"] if same else highest + 1
                    if same:
                        calibration["calibrated_at"] = old_calibration["calibrated_at"]
                    calibration["sha256"] = hashlib.sha256(json.dumps({k:v for k,v in calibration.items() if k != "sha256"}, sort_keys=True, allow_nan=False).encode()).hexdigest()
                old_rules = {r["rule_id"]:r for r in saved.document["rules"]} if saved else {}
                for rule in document["rules"]:
                    old = old_rules.get(rule["rule_id"])
                    if old:
                        changed = any(old[k] != rule[k] for k in ("parameters","enabled")) or saved.document["zones"] != document["zones"] or saved.document.get("calibration") != document.get("calibration") or (rule["parameters"].get("motion_condition") == "moving" and saved.document.get("motion") != document.get("motion"))
                    else:
                        changed = True
                    if changed:
                        previous = history.filter(document__rules__contains=[{"rule_id": rule["rule_id"]}])
                        highest = max((r["version"] for rules in previous.values_list("document__rules", flat=True)
                                       for r in rules if r["rule_id"] == rule["rule_id"]), default=0)
                        rule["version"] = highest + 1
                    else:
                        rule["version"] = old["version"]
                SpatialConfiguration.objects.create(owner=request.user, source_sha256=session.source_sha256,
                    revision=revision+1, document=document)
            session.profile_config = deepcopy(document)
            session.spatial_revision = revision+1
            session.zone = deepcopy(document["zones"][0])
        return Response({"document":document,"revision":revision+1})
