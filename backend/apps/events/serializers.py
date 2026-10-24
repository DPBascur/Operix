import re
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .models import Event
from .pair_contract import EVENT_TYPES, validate_pair, validate_pair_parameters


def has_timezone(value: object) -> bool:
    return isinstance(value, str) and bool(re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value))


class EventSerializer(serializers.ModelSerializer):
    evidence_url = serializers.SerializerMethodField()
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
            "evidence_url",
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

    def validate_occurred_at(self, value):
        if not has_timezone(self.initial_data.get("occurred_at")):
            raise serializers.ValidationError("Se requiere zona horaria explícita.")
        return value

    def validate_rule_parameters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Debe ser un objeto JSON.")
        if value.get("kind") == "person_forklift_proximity":
            validate_pair_parameters(value)
            return value
        expected = {"kind", "class_name", "zone_id", "min_duration_s"}
        if set(value) != expected:
            raise serializers.ValidationError("Claves requeridas: kind, class_name, zone_id, min_duration_s.")
        if value["kind"] != "zone_dwell":
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
        return value

    def validate(self, attrs):
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unknown = set(self.initial_data) - writable
        if unknown:
            raise serializers.ValidationError({"fields": f"Campos no admitidos: {', '.join(sorted(unknown))}."})
        parameters = attrs["rule_parameters"]
        if parameters["kind"] != attrs["event_type"]:
            raise serializers.ValidationError({"event_type": "No coincide con la regla."})
        if parameters["zone_id"] != attrs["zone_id"]:
            raise serializers.ValidationError({"zone_id": "No coincide con la regla."})
        if attrs["event_type"] == "person_forklift_proximity":
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
                   "forklift_weights_sha256", "timestamp_basis", "session_id", "session_run"}
        if set(value) - allowed:
            raise serializers.ValidationError("Metadata de fuente no admitida.")
        for key, item in value.items():
            if key == "session_run":
                if type(item) is not int or item < 1:
                    raise serializers.ValidationError("session_run inválido.")
            elif not isinstance(item, str) or not item or len(item) > 160 or any(c in item for c in ("/", "\\", "\r", "\n")):
                raise serializers.ValidationError("Solo metadata breve, sin rutas locales.")
            if key.endswith("sha256") and not re.fullmatch(r"[0-9a-fA-F]{64}", str(item)):
                raise serializers.ValidationError("SHA-256 inválido.")
        return value


class EventFilterSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=EVENT_TYPES, required=False)
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
