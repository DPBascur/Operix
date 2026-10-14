import re
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .models import Event


def has_timezone(value: object) -> bool:
    return isinstance(value, str) and bool(re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value))


class EventSerializer(serializers.ModelSerializer):
    evidence_url = serializers.SerializerMethodField()
    event_type = serializers.ChoiceField(choices=("zone_dwell",))
    frame_index = serializers.IntegerField(min_value=0, max_value=2147483647)
    track_id = serializers.IntegerField(min_value=0, max_value=2147483647)
    rule_version = serializers.IntegerField(min_value=1, max_value=2147483647)
    video_timestamp_s = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0")
    )
    observed_dwell_time_s = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0")
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
            "evidence_url",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "evidence_url")
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
        for field in ("class_name", "zone_id"):
            if parameters[field] != attrs[field]:
                raise serializers.ValidationError({field: "No coincide con los parámetros de la regla."})
        if attrs["observed_inside"] is not True:
            raise serializers.ValidationError({"observed_inside": "Un candidato zone_dwell debe estar dentro de la zona."})
        if attrs["observed_dwell_time_s"] < Decimal(str(parameters["min_duration_s"])):
            raise serializers.ValidationError({"observed_dwell_time_s": "No alcanza el umbral configurado."})
        return attrs


class EventFilterSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=("zone_dwell",), required=False)
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
