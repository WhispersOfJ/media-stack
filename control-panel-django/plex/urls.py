from django.urls import path

from plex.views import plex_health_partial, plex_page

app_name = "plex_ui"

urlpatterns = [
    path("", plex_page, name="plex_page"),
    path("_health/", plex_health_partial, name="plex_health_partial"),
]