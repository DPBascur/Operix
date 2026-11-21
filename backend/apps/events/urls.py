from django.urls import path

from .views import (EventClipView, EventDetailView, EventEvidenceStatusView, EventEvidenceView,
                    EventFrequencyView, EventListCreateView, SharedIndicatorsView)

urlpatterns = [
    path("events/", EventListCreateView.as_view(), name="event-list"),
    path("events/frequencies/", EventFrequencyView.as_view(), name="event-frequencies"),
    path("indicators/shared/", SharedIndicatorsView.as_view(), name="shared-indicators"),
    path("events/<uuid:pk>/", EventDetailView.as_view(), name="event-detail"),
    path("events/<uuid:pk>/evidence/", EventEvidenceView.as_view(), name="event-evidence"),
    path("events/<uuid:pk>/evidence-status/", EventEvidenceStatusView.as_view(), name="event-evidence-status"),
    path("events/<uuid:pk>/clips/<uuid:run>/", EventClipView.as_view(), name="event-clip"),
]
