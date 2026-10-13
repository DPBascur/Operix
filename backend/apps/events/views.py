import struct
import zlib
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import DatabaseError, connection, transaction
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
        allowed = {"event_type", "occurred_after", "occurred_before"}
        unknown = set(self.request.query_params) - allowed
        if unknown:
            raise ValidationError({"filters": f"Parámetros desconocidos: {', '.join(sorted(unknown))}."})
        filters = EventFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        data = filters.validated_data
        if "event_type" in data:
            queryset = queryset.filter(event_type=data["event_type"])
        if "occurred_after" in data:
            queryset = queryset.filter(occurred_at__gte=data["occurred_after"])
        if "occurred_before" in data:
            queryset = queryset.filter(occurred_at__lte=data["occurred_before"])
        return queryset

    def create(self, request, *args, **kwargs):
        if not settings.EVENT_POST_ENABLED:
            raise PermissionDenied("POST no está habilitado en este entorno.")
        return super().create(request, *args, **kwargs)


class EventDetailView(generics.RetrieveAPIView):
    serializer_class = EventSerializer
    queryset = Event.objects.all()


def validate_png(content):
    """Comprueba estructura PNG y dimensiones sin confiar en nombre o MIME."""
    if len(content) > 2 * 1024 * 1024 or len(content) < 45:
        raise ValidationError({"image": "PNG vacío o superior a 2 MiB."})
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValidationError({"image": "Se requiere PNG válido."})
    offset = 8
    seen_idat = False
    seen_end = False
    first = True
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
            first = False
        elif kind == b"IDAT":
            seen_idat = True
        elif kind == b"IEND" and length == 0:
            seen_end = end == len(content)
            break
        offset = end
    if not (seen_idat and seen_end):
        raise ValidationError({"image": "Estructura PNG inválida."})


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
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=pk)
            if event.evidence_image:
                return Response({"detail": "El evento ya tiene evidencia."}, status=status.HTTP_409_CONFLICT)
            event.evidence_image.save("frame.png", image, save=True)
        return Response(EventSerializer(event, context={"request": request}).data, status=status.HTTP_201_CREATED)
