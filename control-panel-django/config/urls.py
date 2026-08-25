from django.contrib import admin
from django.urls import include, path

from core.views import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("auth_app.urls")),
    path("api/v2/cleanuparr/", include("cleanuparr.api.urls")),
    path("api/v2/nzbdav/", include("nzbdav.api.urls")),
    path("api/v2/host/", include("host_actions.api.urls")),
    path("api/v2/catalog/", include("catalog.api.urls")),
    path("api/v2/watchstate/", include("watchstate.api.urls")),
    path("api/v2/queue/", include("queue_app.api.urls")),
    path("api/v2/host/", include("host.api.urls")),
    path("healthz", healthz),
    path("", include("ui.urls")),
    path("host/", include("host.urls")),
]
