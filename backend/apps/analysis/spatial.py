import hashlib
import json
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.response import Response

from .models import SpatialConfiguration
from .sessions import ROOT, RESTARTABLE
from .sources import latest_spatial
from .validation import validate_spatial
from .views import AnalysisView


class SpatialConfigurationView(AnalysisView):
    def get(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None or session.owner_id != request.user.pk:
            return Response({"detail":"Sesión inexistente"}, status=404)
        with session._guard:
            saved = latest_spatial(request.user.pk, session.source_sha256)
            document = session.operational_config()
            effective, policy = session.policy_configuration(document)
            return Response({"source_sha256": session.source_sha256, "document": document,
                             "revision": saved.revision if saved else 0,
                             "saved": session.with_equipment_profile(saved.document) if saved else None,
                             "effective_rules": effective["rules"], "policy": policy})

    def put(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None or session.owner_id != request.user.pk:
            return Response({"detail":"Sesión inexistente"}, status=404)
        return self.save(request, session, request.data)

    def save(self, request, session, data, *, pattern_confirmed=False):
        if not isinstance(data, dict) or set(data) != {"document","revision"} or type(data["revision"]) is not int:
            return Response({"detail":"Indique documento y revisión"}, status=400)
        with session._guard:
            if session._closed or session.state not in RESTARTABLE or (session.process and session.process.poll() is None):
                return Response({"detail":"Detenga el análisis antes de editar"}, status=409)
            submitted = data["document"]
            configured_profile = (session.profile_config or {}).get("equipment_profile")
            if pattern_confirmed:
                submitted = session.with_equipment_profile(submitted)
            elif isinstance(submitted, dict) and submitted.get("equipment_profile") != configured_profile:
                return Response({"detail": "El perfil de equipo se administra en la configuración del servidor."}, status=400)
            try:
                document = validate_spatial(submitted, session.source_sha256, ROOT)
            except ValueError as error:
                return Response({"detail": str(error)}, status=400)
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                history = SpatialConfiguration.objects.filter(owner=request.user, source_sha256=session.source_sha256).order_by("-revision")
                saved = history.first()
                revision = saved.revision if saved else 0
                if revision != data["revision"]:
                    return Response({"detail":"La configuración cambió. Recupere la revisión actual."}, status=409)
                calibration_version = 0
                rule_versions = defaultdict(int)
                for old_document in history.values_list("document", flat=True).iterator():
                    calibration_version = max(calibration_version, (old_document.get("calibration") or {}).get("version", 0))
                    for old_rule in old_document["rules"]:
                        rule_id = old_rule["rule_id"]
                        rule_versions[rule_id] = max(rule_versions[rule_id], old_rule["version"])
                calibration = document.get("calibration")
                old_calibration = saved.document.get("calibration") if saved else None
                if calibration:
                    if calibration.get("pattern_evidence") and not pattern_confirmed:
                        compatible = old_calibration and all(
                            calibration.get(key) == old_calibration.get(key) for key in (
                                "pattern_evidence", "image_points", "ground_points_m", "framing_reference",
                            )
                        )
                        if not compatible or (old_calibration["status"] == "invalid" and calibration["status"] == "valid"):
                            return Response({"detail": "Confirme una nueva propuesta de patrón."}, status=400)
                    keys = ("image_points", "ground_points_m", "status", "zones_reviewed", "framing_reference", "pattern_evidence")
                    same = old_calibration and all(calibration.get(k) == old_calibration.get(k) for k in keys)
                    calibration["version"] = old_calibration["version"] if same else calibration_version + 1
                    if same:
                        calibration["calibrated_at"] = old_calibration["calibrated_at"]
                    calibration["sha256"] = hashlib.sha256(json.dumps({k:v for k,v in calibration.items() if k != "sha256"}, sort_keys=True, allow_nan=False).encode()).hexdigest()
                old_rules = {r["rule_id"]:r for r in saved.document["rules"]} if saved else {}
                for rule in document["rules"]:
                    old = old_rules.get(rule["rule_id"])
                    if old:
                        uses_motion = (
                            rule["parameters"].get("motion_condition") == "moving"
                            or rule["parameters"].get("exclude_possible_occupant") is True
                        )
                        changed = (
                            any(old[k] != rule[k] for k in ("parameters", "enabled"))
                            or saved.document["zones"] != document["zones"]
                            or saved.document.get("calibration") != document.get("calibration")
                            or (uses_motion and saved.document.get("motion") != document.get("motion"))
                            or ("equipment_category" in rule["parameters"]
                                and saved.document.get("equipment_profile") != document.get("equipment_profile"))
                        )
                    else:
                        changed = True
                    if changed:
                        rule["version"] = rule_versions[rule["rule_id"]] + 1
                    else:
                        rule["version"] = old["version"]
                SpatialConfiguration.objects.create(owner=request.user, source_sha256=session.source_sha256,
                    revision=revision+1, document=document)
            session.apply_spatial(document, revision + 1)
        return Response({"document":document,"revision":revision+1})
