"""Source inventory, including spatial revisions created before the inventory existed."""

from django.db.models import OuterRef, Subquery
from django.urls import reverse
from rest_framework.response import Response

from .catalog import SHA256, load_catalog, resolve_policy
from .catalog_views import CatalogReadWriteView
from .models import AnalysisSource, SpatialConfiguration
from .sessions import opened_sources, read_profile


def latest_spatial(owner_id, source_sha256):
    return SpatialConfiguration.objects.filter(owner_id=owner_id, source_sha256=source_sha256).order_by("-revision").first()


def serialize_zones(document, rules, updated_at):
    links = {}
    for rule in rules:
        parameters = rule["parameters"]
        links.setdefault(parameters.get("zone_id"), []).append({
            "rule_id": rule["rule_id"], "kind": parameters.get("kind"),
            "enabled": rule["enabled"], "version": rule["version"],
        })
    return [{
        "zone_id": zone["zone_id"], "name": zone["name"], "polygon": zone["polygon"],
        "geometry_type": "polygon", "purpose": zone.get("purpose", "observation"),
        "enabled": zone.get("enabled", True), "updated_at": updated_at,
        "rules": links.get(zone["zone_id"], []),
    } for zone in document["zones"] if zone.get("polygon")]


def serialize_source(source_sha256, source, revision, session, entries, can_edit):
    document = None
    session_id = None
    metadata = source
    if session is not None:
        with session._guard:
            if not session._closed:
                session_id = session.id
                metadata = session
                profile, demo_source_id = session.profile, session.demo_source_id
                document = session.operational_config()
    if session_id is None:
        profile = source.profile if source else None
        demo_source_id = source.demo_source_id if source else None
        if demo_source_id is not None and revision is None:
            try:
                document = read_profile(profile)
            except (OSError, ValueError, KeyError):
                pass
    if revision is not None:
        document = revision.document
    rules, policy = resolve_policy(entries, profile=profile, demo_source_id=demo_source_id,
                                   source_sha256=source_sha256)
    updated = revision.created_at if revision else (source.updated_at if source else None)
    updated_at = updated.isoformat() if updated else None
    can_open_session = can_edit and session_id is not None
    result = {
        "source_sha256": source_sha256, "filename": metadata.filename if metadata else None,
        "profile": profile, "source_kind": metadata.source_kind if metadata else None,
        "demo_source_id": demo_source_id, "source_bytes": metadata.source_bytes if metadata else None,
        "revision": revision.revision if revision else 0, "updated_at": updated_at,
        "zones": [],
        "policy": policy,
        "session_id": str(session_id) if can_open_session else None,
        "video_url": reverse("analysis-session-source", args=[session_id]) if can_open_session else None,
        "configuration_url": reverse("analysis-configuration", args=[session_id]) if can_open_session else None,
        "session_create_url": reverse("analysis-session-create"), "can_edit": can_edit,
    }
    if document is not None:
        effective_rules = document["rules"] if rules is None else rules
        result["effective_rules"] = effective_rules
        result["zones"] = serialize_zones(document, effective_rules, updated_at)
    return result


class SourceListView(CatalogReadWriteView):
    def get(self, request):
        owner = request.user.pk
        can_edit = self.can_edit(request)
        sessions = opened_sources(owner)
        revisions = SpatialConfiguration.objects.filter(owner_id=owner)
        latest = revisions.filter(source_sha256=OuterRef("source_sha256")).order_by("-revision")
        by_hash = {row.source_sha256: row for row in revisions.filter(pk=Subquery(latest.values("pk")[:1]))}
        sources = {row.source_sha256: row for row in AnalysisSource.objects.filter(owner_id=owner)}
        entries = load_catalog(owner)
        result = [
            serialize_source(sha256, sources.get(sha256), by_hash.get(sha256), sessions.get(sha256),
                             entries, can_edit)
            for sha256 in sources.keys() | by_hash.keys()
        ]
        result.sort(key=lambda row: (row["updated_at"] or "", row["source_sha256"]), reverse=True)
        return Response({"sources": result, "can_edit": can_edit})


class SourceDetailView(CatalogReadWriteView):
    def get(self, request, source_sha256):
        if not SHA256.fullmatch(source_sha256):
            return Response({"detail": "Fuente inexistente"}, status=404)
        owner = request.user.pk
        source = AnalysisSource.objects.filter(owner_id=owner, source_sha256=source_sha256).first()
        revision = latest_spatial(owner, source_sha256)
        if source is None and revision is None:
            return Response({"detail": "Fuente inexistente"}, status=404)
        return Response(serialize_source(source_sha256, source, revision, opened_sources(owner).get(source_sha256),
                                         load_catalog(owner), self.can_edit(request)))
