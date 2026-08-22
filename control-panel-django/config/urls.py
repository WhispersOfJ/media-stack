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
    path("healthz", healthz),
]
