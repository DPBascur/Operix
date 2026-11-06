from django.urls import path

from .views import EventClipView, EventDetailView, EventEvidenceView, EventFrequencyView, EventListCreateView

urlpatterns = [
    path("events/", EventListCreateView.as_view(), name="event-list"),
    path("events/frequencies/", EventFrequencyView.as_view(), name="event-frequencies"),
    path("events/<uuid:pk>/", EventDetailView.as_view(), name="event-detail"),
    path("events/<uuid:pk>/evidence/", EventEvidenceView.as_view(), name="event-evidence"),
    path("events/<uuid:pk>/clips/<uuid:run>/", EventClipView.as_view(), name="event-clip"),
]
