from django.conf import settings
from django.db import DatabaseError, connection
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

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
