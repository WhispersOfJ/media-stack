from django.contrib import admin
from django.urls import include, path

from core.views import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("auth_app.urls")),
    path("api/v2/ratings/", include("ratings.api.urls")),
    path("api/v2/seerr/", include("seerr.api.urls")),
    path("api/v2/prowlarr/", include("prowlarr.api.urls")),
    path("api/v2/radarr/", include("radarr.api.urls")),
    path("api/v2/sonarr/", include("sonarr.api.urls")),
    path("api/v2/cleanuparr/", include("cleanuparr.api.urls")),
    path("api/v2/nzbdav/", include("nzbdav.api.urls")),
    path("api/v2/host/", include("host_actions.api.urls")),
    path("api/v2/catalog/", include("catalog.api.urls")),
    path("api/v2/watchstate/", include("watchstate.api.urls")),
    path("api/v2/mdblist/", include("mdblist.api.urls")),
    path("api/v2/letterboxd/", include("letterboxd.api.urls")),
    path("api/v2/plex/", include("plex.api.urls")),
    path("api/v2/queue/", include("queue_app.api.urls")),
    path("api/v2/posters/", include("posters.api.urls")),
    path("healthz", healthz),
]
