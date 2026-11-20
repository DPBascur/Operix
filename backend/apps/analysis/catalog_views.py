from django.shortcuts import get_object_or_404
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from config.access import CanAnalyze, HasOperixRole, request_role

from .catalog import save_entry
from .models import AnalysisRunSnapshot, RuleCatalogEntry


class CatalogReadWriteView(APIView):
    def get_permissions(self):
        permission = HasOperixRole if self.request.method in SAFE_METHODS else CanAnalyze
        return [permission()]

    def can_edit(self, request):
        return request_role(request) in {"administrator", "safety_lead"}


def serialize_entry(entry):
    return {"id": str(entry.pk), **entry.document, "version": entry.version,
            "updated_at": entry.updated_at.isoformat()}


class CatalogListView(CatalogReadWriteView):
    kind = None

    def get(self, request):
        entries = RuleCatalogEntry.objects.filter(owner=request.user, kind=self.kind).order_by("-updated_at", "id")
        return Response({"results": [serialize_entry(entry) for entry in entries],
                         "can_edit": self.can_edit(request)})

    def post(self, request):
        return Response(serialize_entry(save_entry(request.user.pk, self.kind, request.data)), status=201)


class CatalogEntryView(CatalogReadWriteView):
    kind = None

    def get(self, request, pk):
        entry = get_object_or_404(RuleCatalogEntry, owner=request.user, kind=self.kind, pk=pk)
        return Response(serialize_entry(entry))

    def put(self, request, pk):
        return Response(serialize_entry(save_entry(request.user.pk, self.kind, request.data, pk)))


class CatalogHistoryView(CatalogReadWriteView):
    kind = None

    def get(self, request, pk):
        entry = get_object_or_404(RuleCatalogEntry, owner=request.user, kind=self.kind, pk=pk)
        return Response({"results": [
            {"id": str(entry.pk), **revision.document, "version": revision.version,
             "created_at": revision.created_at.isoformat()}
            for revision in entry.history.order_by("-version")
        ]})


class RunSnapshotView(CatalogReadWriteView):
    def get(self, request, pk):
        snapshot = get_object_or_404(AnalysisRunSnapshot, owner=request.user, pk=pk)
        return Response({"id": str(snapshot.pk), "source_sha256": snapshot.source_sha256,
                         "profile": snapshot.profile, "spatial_revision": snapshot.spatial_revision,
                         "document": snapshot.configuration, "config_sha256": snapshot.config_sha256,
                         "policy": snapshot.policy, "created_at": snapshot.created_at.isoformat()})
