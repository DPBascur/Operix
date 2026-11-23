import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils.timezone import now
from rest_framework import serializers

from .clips import clip_info
from .models import Event
from .pair_contract import EVENT_TYPES, validate_pair, validate_pair_parameters


def has_timezone(value: object) -> bool:
    return isinstance(value, str) and bool(re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value))


class EventSerializer(serializers.ModelSerializer):
    evidence_url = serializers.SerializerMethodField()
    evidence_status = serializers.SerializerMethodField()
    evidence_pending = serializers.BooleanField(write_only=True, required=False)
    event_type = serializers.ChoiceField(choices=EVENT_TYPES)
    frame_index = serializers.IntegerField(min_value=0, max_value=2147483647)
    track_id = serializers.IntegerField(min_value=0, max_value=2147483647, required=False, allow_null=True)
    rule_version = serializers.IntegerField(min_value=1, max_value=2147483647)
    video_timestamp_s = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0")
    )
    observed_dwell_time_s = serializers.DecimalField(
        max_digits=18, decimal_places=9, min_value=Decimal("0"), required=False, allow_null=True
    )

    class Meta:
        model = Event
        fields = (
            "id",
            "analysis_run_id",
            "view_id",
            "occurred_at",
            "video_timestamp_s",
            "frame_index",
            "event_type",
            "rule_id",
            "rule_version",
            "rule_parameters",
            "zone_id",
            "track_id",
            "class_name",
            "observed_inside",
            "observed_dwell_time_s",
            "interaction", "observations", "episode", "source", "pair_key",
            "evidence_url", "evidence_status", "evidence_pending",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "evidence_url", "pair_key")
        extra_kwargs = {"class_name": {"required": False}, "observed_inside": {"required": False}}
        # El POST repetido se resuelve en la vista con la constraint de PostgreSQL;
        # el validador automático de unicidad de DRF lo convertiría en 400.
        validators = []

    def get_evidence_url(self, obj):
        if not obj.evidence_image or not obj.evidence_image.storage.exists(obj.evidence_image.name):
            return None
        from django.urls import reverse

        return reverse("event-evidence", kwargs={"pk": obj.pk})

    def get_evidence_status(self, obj):
        if not obj.evidence_stage:
            return None
        png = self.get_evidence_url(obj) is not None
        clip = (self.context["event_clip"] if "event_clip" in self.context else clip_info(obj)) is not None
        if png and clip:
            return "ready"
        # Bound pending after a hard stop or unavailable publisher. A late successful
        # upload remains visible without reopening the original publication.
        if obj.evidence_stage == Event.EvidenceStage.PENDING and now() - obj.created_at < timedelta(minutes=5):
            return "pending"
        return "partial" if png or clip else "failed"

    def validate_occurred_at(self, value):
        if not has_timezone(self.initial_data.get("occurred_at")):
            raise serializers.ValidationError("Se requiere zona horaria explícita.")
        return value

    def validate_rule_parameters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Debe ser un objeto JSON.")
        if value.get("kind") in {"person_forklift_proximity", "zone_coexistence"}:
            validate_pair_parameters(value)
            return value
        expected = {"kind", "class_name", "zone_id", "min_duration_s"}
        if set(value) != expected:
            raise serializers.ValidationError("Claves requeridas: kind, class_name, zone_id, min_duration_s.")
        if value["kind"] not in {"zone_dwell", "zone_entry"}:
            raise serializers.ValidationError("Solo se admite kind=zone_dwell en esta versión.")
        if not all(isinstance(value[key], str) and value[key].strip() for key in ("class_name", "zone_id")):
            raise serializers.ValidationError("class_name y zone_id deben ser textos no vacíos.")
        duration = value["min_duration_s"]
        if type(duration) not in (int, float):
            raise serializers.ValidationError("min_duration_s debe ser numérico, finito y no negativo.")
        try:
            decimal_duration = Decimal(str(duration))
        except InvalidOperation as error:
            raise serializers.ValidationError("min_duration_s no es un número válido.") from error
        if not decimal_duration.is_finite() or not 0 <= decimal_duration <= Decimal("999999999.999"):
            raise serializers.ValidationError("min_duration_s debe ser numérico, finito y no negativo.")
        if value["kind"] == "zone_entry" and duration != 0:
            raise serializers.ValidationError("El ingreso observado usa duración cero.")
        return value

    def validate(self, attrs):
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unknown = set(self.initial_data) - writable
        if unknown:
            raise serializers.ValidationError({"fields": f"Campos no admitidos: {', '.join(sorted(unknown))}."})
        if attrs.get("evidence_pending") and attrs.get("source", {}).get("kind") != "lab":
            raise serializers.ValidationError({"evidence_pending": "Reservado a eventos del laboratorio."})
        parameters = attrs["rule_parameters"]
        if parameters["kind"] != attrs["event_type"]:
            raise serializers.ValidationError({"event_type": "No coincide con la regla."})
        if parameters["zone_id"] != attrs["zone_id"]:
            raise serializers.ValidationError({"zone_id": "No coincide con la regla."})
        if attrs["event_type"] in {"person_forklift_proximity", "zone_coexistence"}:
            return validate_pair(attrs)
        if any(attrs.get(field) for field in ("interaction", "observations", "episode")):
            raise serializers.ValidationError("zone_dwell no admite un snapshot por pares.")
        if any(attrs.get(field) is None for field in ("track_id", "class_name", "observed_inside", "observed_dwell_time_s")):
            raise serializers.ValidationError("zone_dwell requiere sus observaciones originales.")
        for field in ("class_name", "zone_id"):
            if parameters[field] != attrs[field]:
                raise serializers.ValidationError({field: "No coincide con los parámetros de la regla."})
        if attrs["observed_inside"] is not True:
            raise serializers.ValidationError({"observed_inside": "Un candidato zone_dwell debe estar dentro de la zona."})
        # Misma tolerancia NUMÉRICA del Motor, no gracia operacional.
        shortfall = Decimal(str(parameters["min_duration_s"])) - attrs["observed_dwell_time_s"]
        if shortfall > Decimal("0.000000001"):
            raise serializers.ValidationError({"observed_dwell_time_s": "No alcanza el umbral configurado."})
        return attrs

    def validate_source(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("source debe ser un objeto.")
        allowed = {"filename", "kind", "video_sha256", "config_sha256", "person_weights_sha256",
                   "forklift_weights_sha256", "timestamp_basis", "session_id", "session_run", "perception",
                   "spatial_configuration", "spatial_revision", "epoch", "camera_id", "capture"}
        if set(value) - allowed:
            raise serializers.ValidationError("Metadata de fuente no admitida.")
        if value.get("kind") == "lab":
            if not {"camera_id", "capture", "video_sha256", "config_sha256"} <= value.keys():
                raise serializers.ValidationError("Trazabilidad de laboratorio incompleta.")
            if value.get("timestamp_basis") != "LAB_RECEPTION_UTC":
                raise serializers.ValidationError("Base temporal de laboratorio inválida.")
        elif "camera_id" in value or "capture" in value:
            raise serializers.ValidationError("Metadata de captura reservada al laboratorio.")
        for key, item in value.items():
            if key == "capture":
                fields = {"received_at", "processed_at", "source_pts_s", "time_basis"}
                if not isinstance(item, dict) or set(item) != fields:
                    raise serializers.ValidationError("Tiempos de captura incompletos.")
                utc = serializers.DateTimeField()
                if any(not has_timezone(item[field]) for field in ("received_at", "processed_at")):
                    raise serializers.ValidationError("Los tiempos de captura requieren zona horaria.")
                received = utc.run_validation(item["received_at"])
                processed = utc.run_validation(item["processed_at"])
                pts = item["source_pts_s"]
                if (processed < received or item["time_basis"] not in ("source_pts", "local_arrival")
                        or (pts is not None and (type(pts) not in (int, float) or not 0 <= pts <= 1e12))):
                    raise serializers.ValidationError("Tiempos de captura incompatibles.")
                continue
            if key == "camera_id" and (
                not isinstance(item, str) or not re.fullmatch(r"lab-cam-[0-9]{2}", item)
            ):
                raise serializers.ValidationError("Identidad de cámara inválida.")
            if key == "spatial_configuration":
                if not isinstance(item, dict) or set(item) - {"schema_version","view_id","coordinate_system","zones","rules","calibration","motion","relations"}:
                    raise serializers.ValidationError("Snapshot espacial inválido")
            elif key == "perception":
                if not isinstance(item, dict) or set(item) != {"person", "forklift"}:
                    raise serializers.ValidationError("Metadata de percepción inválida.")
                for name, config in item.items():
                    expected = {"model_id", "weights_sha256", "class_filter", "imgsz", "confidence", "nms_iou"}
                    if not isinstance(config, dict) or set(config) != expected:
                        raise serializers.ValidationError("Configuración de percepción incompleta.")
                    if (not isinstance(config["model_id"], str)
                            or not re.fullmatch(r"[A-Z0-9_]{1,64}", config["model_id"])
                            or not isinstance(config["weights_sha256"], str)
                            or not re.fullmatch(r"[0-9a-fA-F]{64}", config["weights_sha256"])
                            or config["weights_sha256"] != value.get(name + "_weights_sha256")
                            or config["class_filter"] != name
                            or type(config["imgsz"]) is not int or not 1 <= config["imgsz"] <= 4096
                            or any(type(config[k]) not in (int, float) or not 0 <= config[k] <= 1
                                   for k in ("confidence", "nms_iou"))):
                        raise serializers.ValidationError("Configuración de percepción inválida.")
            elif key == "epoch":
                if type(item) is not int or item < 0:
                    raise serializers.ValidationError("Epoca inv\u00e1lida")
            elif key in {"session_run", "spatial_revision"}:
                if type(item) is not int or item < 1:
                    raise serializers.ValidationError(f"{key} debe ser un entero positivo.")
            elif not isinstance(item, str) or not item or len(item) > 160 or any(c in item for c in ("/", "\\", "\r", "\n")):
                raise serializers.ValidationError("Solo metadata breve, sin rutas locales.")
            if key.endswith("sha256") and not re.fullmatch(r"[0-9a-fA-F]{64}", str(item)):
                raise serializers.ValidationError("SHA-256 inválido.")
        return value


class EventFilterSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=EVENT_TYPES, required=False)
    zone_id = serializers.CharField(max_length=64, trim_whitespace=False, required=False)
    source_kind = serializers.ChoiceField(choices=("demo", "manual", "unknown", "lab"), required=False)
    camera_id = serializers.RegexField(r"^lab-cam-[0-9]{2}$", required=False)
    source_sha256 = serializers.RegexField(r"^[a-f0-9]{64}$", required=False)
    occurred_after = serializers.DateTimeField(required=False)
    occurred_before = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        for field in ("occurred_after", "occurred_before"):
            if field in attrs and not has_timezone(self.initial_data.get(field)):
                raise serializers.ValidationError({field: "Se requiere zona horaria explícita."})
        if attrs.get("occurred_after") and attrs.get("occurred_before"):
            if attrs["occurred_after"] > attrs["occurred_before"]:
                raise serializers.ValidationError("occurred_after no puede superar occurred_before.")
        return attrs


class EventHistorySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=2**53 - 1)
    page_size = serializers.ChoiceField(choices=(15, 60), default=15)
    evidence_stage = serializers.ChoiceField(
        choices=("pending", "finished", "legacy"), required=False,
    )
    search = serializers.CharField(max_length=120, required=False)
    order = serializers.ChoiceField(choices=("newest", "oldest"), default="newest")
