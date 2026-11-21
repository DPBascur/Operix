from .cameras import CameraDetailView, CameraInventoryView, CameraPreviewView, CameraStartView, CameraStopView
from django.urls import path

from .calibration_views import CameraCalibrationView, SessionCalibrationView
from .catalog_views import CatalogEntryView, CatalogHistoryView, CatalogListView, RunSnapshotView
from .models import RuleCatalogEntry
from .sources import SourceDetailView, SourceListView
from .spatial import SpatialConfigurationView

from .views import (
    DemoSourceView, ProfileListView, SessionDetailView, SessionListView,
    SessionResultView, SessionSourceView, SessionStartView, SessionStopView,
    SessionStreamView, SessionZoneView,
    SessionPersistenceRetryView,
)

urlpatterns = [
    path("analysis/cameras/", CameraInventoryView.as_view(), name="lab-camera-list"),
    path("analysis/cameras/<slug:camera_id>/", CameraDetailView.as_view(), name="lab-camera-detail"),
    path("analysis/cameras/<slug:camera_id>/start/", CameraStartView.as_view(), name="lab-camera-start"),
    path("analysis/cameras/<slug:camera_id>/stop/", CameraStopView.as_view(), name="lab-camera-stop"),
    path("analysis/cameras/<slug:camera_id>/preview/", CameraPreviewView.as_view(), name="lab-camera-preview"),
    path("analysis/cameras/<slug:camera_id>/calibration/proposal/", CameraCalibrationView.as_view(), name="lab-camera-calibration-proposal"),
    path("analysis/cameras/<slug:camera_id>/calibration/confirm/", CameraCalibrationView.as_view(confirm=True), name="lab-camera-calibration-confirm"),
    path("analysis/sources/", SourceListView.as_view(), name="analysis-source-list"),
    path("analysis/sources/<str:source_sha256>/", SourceDetailView.as_view(), name="analysis-source-detail"),
    path("analysis/run-snapshots/<uuid:pk>/", RunSnapshotView.as_view(), name="analysis-run-snapshot"),
    path("analysis/sessions/<uuid:pk>/configuration/", SpatialConfigurationView.as_view(), name="analysis-configuration"),
    path("analysis/sessions/<uuid:pk>/calibration/proposal/", SessionCalibrationView.as_view(), name="analysis-calibration-proposal"),
    path("analysis/sessions/<uuid:pk>/calibration/confirm/", SessionCalibrationView.as_view(confirm=True), name="analysis-calibration-confirm"),
    path("analysis/profiles/", ProfileListView.as_view(), name="analysis-profile-list"),
    path(
        "analysis/profiles/<str:profile>/demo/<str:source_id>/",
        DemoSourceView.as_view(), name="analysis-demo-source",
    ),
    path("analysis/sessions/", SessionListView.as_view(), name="analysis-session-create"),
    path("analysis/sessions/<uuid:pk>/status/", SessionDetailView.as_view(), name="analysis-session-status"),
    path("analysis/sessions/<uuid:pk>/start/", SessionStartView.as_view(), name="analysis-session-start"),
    path("analysis/sessions/<uuid:pk>/stop/", SessionStopView.as_view(), name="analysis-session-stop"),
    path("analysis/sessions/<uuid:pk>/persistence/retry/", SessionPersistenceRetryView.as_view(), name="analysis-persistence-retry"),
    path("analysis/sessions/<uuid:pk>/zone/", SessionZoneView.as_view(), name="analysis-session-zone"),
    path("analysis/sessions/<uuid:pk>/stream/", SessionStreamView.as_view(), name="analysis-session-stream"),
    path("analysis/sessions/<uuid:pk>/source/", SessionSourceView.as_view(), name="analysis-session-source"),
    path("analysis/sessions/<uuid:pk>/result/", SessionResultView.as_view(), name="analysis-session-result"),
    path("analysis/sessions/<uuid:pk>/", SessionDetailView.as_view(), name="analysis-session-delete"),
]

for resource, kind in (
    ("rule-templates", RuleCatalogEntry.Kind.TEMPLATE),
    ("rule-sets", RuleCatalogEntry.Kind.SET),
    ("rule-assignments", RuleCatalogEntry.Kind.ASSIGNMENT),
):
    urlpatterns += [
        path(f"analysis/{resource}/", CatalogListView.as_view(kind=kind), name=f"analysis-{resource}"),
        path(f"analysis/{resource}/<uuid:pk>/", CatalogEntryView.as_view(kind=kind),
             name=f"analysis-{resource}-detail"),
        path(f"analysis/{resource}/<uuid:pk>/history/", CatalogHistoryView.as_view(kind=kind),
             name=f"analysis-{resource}-history"),
    ]
