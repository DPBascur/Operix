from django.urls import path

from .views import (
    DemoSourceView, ProfileListView, SessionDetailView, SessionListView,
    SessionResultView, SessionSourceView, SessionStartView, SessionStopView,
    SessionStreamView, SessionZoneView,
    SessionPersistenceRetryView,
)

urlpatterns = [
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
