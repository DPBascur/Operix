from django.urls import path

from .views import EventDetailView, EventEvidenceView, EventListCreateView

urlpatterns = [
    path("events/", EventListCreateView.as_view(), name="event-list"),
    path("events/<uuid:pk>/", EventDetailView.as_view(), name="event-detail"),
    path("events/<uuid:pk>/evidence/", EventEvidenceView.as_view(), name="event-evidence"),
]
