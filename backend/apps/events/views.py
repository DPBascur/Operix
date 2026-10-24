import struct
import zlib
from decimal import Decimal, InvalidOperation
from datetime import timezone

from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Event
from .serializers import EventFilterSerializer, EventSerializer


@api_view(["GET"])
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return Response({"status": "degraded", "database": "unavailable"}, status=503)
    return Response({"status": "ok", "database": "ok"})


class EventListCreateView(generics.ListCreateAPIView):
    serializer_class = EventSerializer
    queryset = Event.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.method != "GET":
            return queryset
        return filtered_events(queryset, self.request.query_params)

    def create(self, request, *args, **kwargs):
        if not settings.EVENT_POST_ENABLED:
            raise PermissionDenied("POST no está habilitado en este entorno.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        identity_fields = (
            "analysis_run_id", "view_id", "frame_index", "rule_id",
            "rule_version", "track_id", "class_name", "zone_id",
        )
        if values["event_type"] == "person_forklift_proximity":
            identity_fields = ("analysis_run_id", "view_id", "frame_index", "rule_id",
                               "rule_version", "pair_key", "zone_id")
        identity = {field: values[field] for field in identity_fields}
        defaults = {field: value for field, value in values.items() if field not in identity}
        event, created = Event.objects.get_or_create(defaults=defaults, **identity)
        if not created:
            # El reloj civil puede ser una ancla de análisis distinta en un retry;
            # la primera fecha persistida se conserva. El resto debe coincidir.
            if any(
                getattr(event, field) != value
                for field, value in defaults.items()
                if field != "occurred_at"
            ):
                return Response(
                    {"detail": "La identidad de evento ya existe con datos incompatibles."},
                    status=status.HTTP_409_CONFLICT,
                )
        data = self.get_serializer(event).data
        data["created"] = created
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class EventDetailView(generics.RetrieveAPIView):
    serializer_class = EventSerializer
    queryset = Event.objects.all()


def filtered_events(queryset, query_params):
    """Comparte el contrato de filtros y sus límites inclusivos con la lista."""
    unknown = set(query_params) - {"event_type", "occurred_after", "occurred_before"}
    if unknown:
        raise ValidationError({"filters": f"Parámetros desconocidos: {', '.join(sorted(unknown))}."})
    filters = EventFilterSerializer(data=query_params)
    filters.is_valid(raise_exception=True)
    data = filters.validated_data
    if "event_type" in data:
        queryset = queryset.filter(event_type=data["event_type"])
    if "occurred_after" in data:
        queryset = queryset.filter(occurred_at__gte=data["occurred_after"])
    if "occurred_before" in data:
        queryset = queryset.filter(occurred_at__lte=data["occurred_before"])
    return queryset


class EventFrequencyView(APIView):
    """Frecuencias UTC de eventos persistidos, no indicadores de riesgo."""

    def get(self, request):
        queryset = filtered_events(Event.objects.all(), request.query_params)
        grouped = queryset.annotate(day=TruncDate("occurred_at", tzinfo=timezone.utc)).values(
            "day", "event_type",
        ).order_by("day", "event_type").annotate(count=Count("id"))
        by_day, by_type = {}, {}
        for row in grouped:
            day, event_type, count = row["day"].isoformat(), row["event_type"], row["count"]
            by_day[day] = by_day.get(day, 0) + count
            by_type[event_type] = by_type.get(event_type, 0) + count
        return Response({
            "total": sum(by_day.values()), "timezone": "UTC", "period": "day",
            "by_period": [{"date": day, "count": count} for day, count in sorted(by_day.items())],
            "by_type": [{"event_type": name, "count": count} for name, count in sorted(by_type.items())],
        })


def validate_png(content):
    """Valida chunks y scanlines PNG con descompresión acotada, sin nuevas dependencias."""
    if len(content) > 2 * 1024 * 1024 or len(content) < 45:
        raise ValidationError({"image": "PNG vacío o superior a 2 MiB."})
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValidationError({"image": "Se requiere PNG válido."})
    offset = 8
    seen_idat = False
    seen_end = False
    first = True
    compressed = []
    header = None
    palette = False
    while offset + 12 <= len(content):
        length = struct.unpack(">I", content[offset:offset + 4])[0]
        end = offset + 12 + length
        if end > len(content):
            break
        kind = content[offset + 4:offset + 8]
        body = content[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", content[end - 4:end])[0]
        if zlib.crc32(kind + body) != crc:
            break
        if first:
            if kind != b"IHDR" or length != 13:
                break
            width, height = struct.unpack(">II", body[:8])
            if not (0 < width <= 4096 and 0 < height <= 4096):
                break
            depth, color, compression, filtering, interlace = body[8:]
            allowed_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16},
                              3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if (depth not in allowed_depths.get(color, set()) or compression != 0
                    or filtering != 0 or interlace not in (0, 1)):
                break
            header = (width, height, depth, color, interlace)
            first = False
        elif kind == b"IDAT":
            seen_idat = True
            compressed.append(body)
        elif kind == b"PLTE":
            palette = 0 < length <= 768 and length % 3 == 0
        elif kind == b"IHDR":
            break
        elif kind == b"IEND" and length == 0:
            seen_end = end == len(content)
            break
        offset = end
    if not (seen_idat and seen_end):
        raise ValidationError({"image": "Estructura PNG inválida."})
    width, height, depth, color, interlace = header
    if color == 3 and not palette:
        raise ValidationError({"image": "PNG indexado sin paleta válida."})
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    # Adam7: dimensiones de cada pasada; no requiere reconstruir una imagen gigante.
    passes = ((0, 0, 1, 1),) if not interlace else (
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2),
    )
    rows = []
    for x, y, dx, dy in passes:
        w, h = max(0, (width - x + dx - 1) // dx), max(0, (height - y + dy - 1) // dy)
        if w and h:
            rows.extend([1 + (w * channels * depth + 7) // 8] * h)
    expected = sum(rows)
    if expected > 64 * 1024 * 1024:
        raise ValidationError({"image": "PNG supera el límite de 64 MiB descomprimidos."})
    decoder = zlib.decompressobj()
    try:
        pixels = decoder.decompress(b"".join(compressed), expected + 1)
    except zlib.error:
        raise ValidationError({"image": "Datos de imagen PNG inválidos."}) from None
    if (len(pixels) != expected or not decoder.eof or decoder.unused_data
            or decoder.unconsumed_tail):
        raise ValidationError({"image": "Datos de imagen PNG incompletos o excesivos."})
    offset = 0
    for length in rows:
        if pixels[offset] > 4:
            raise ValidationError({"image": "Filtro de scanline PNG inválido."})
        offset += length


class EventEvidenceView(APIView):
    parser_classes = (MultiPartParser,)

    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        if not event.evidence_image:
            raise Http404("Evento sin evidencia")
        try:
            source = event.evidence_image.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404("Evidencia no disponible")
        response = FileResponse(source, content_type="image/png")
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def post(self, request, pk):
        if not settings.EVENT_POST_ENABLED:
            raise PermissionDenied("POST no está habilitado en este entorno.")
        event = get_object_or_404(Event, pk=pk)
        try:
            frame_index = int(request.data.get("frame_index", ""))
            timestamp = Decimal(str(request.data.get("video_timestamp_s", "")))
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError("frame_index o video_timestamp_s inválido.")
        if frame_index != event.frame_index or timestamp != event.video_timestamp_s:
            raise ValidationError("La evidencia no corresponde al frame y tiempo del evento.")
        image = request.FILES.get("image")
        if image is None or image.size > 2 * 1024 * 1024:
            raise ValidationError({"image": "Se requiere PNG de hasta 2 MiB."})
        content = image.read()
        validate_png(content)
        image.seek(0)
        written = None
        try:
            with transaction.atomic():
                event = Event.objects.select_for_update().get(pk=pk)
                if event.evidence_image and event.evidence_image.storage.exists(event.evidence_image.name):
                    return Response(
                        EventSerializer(event, context={"request": request}).data,
                        status=status.HTTP_200_OK,
                    )
                event.evidence_image.save("frame.png", image, save=False)
                written = event.evidence_image.name
                event.save(update_fields=["evidence_image"])
        except Exception:
            if written:
                event.evidence_image.storage.delete(written)
            raise
        return Response(EventSerializer(event, context={"request": request}).data, status=status.HTTP_201_CREATED)
