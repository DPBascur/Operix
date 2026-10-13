from django.urls import path

from .views import EventDetailView, EventListCreateView

urlpatterns = [
    path("events/", EventListCreateView.as_view(), name="event-list"),
    path("events/<uuid:pk>/", EventDetailView.as_view(), name="event-detail"),
]
