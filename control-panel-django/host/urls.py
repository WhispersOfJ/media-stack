from django.urls import path

from host.views import (
    container_restart,
    container_start,
    container_stop,
    host_page,
    host_vitals_partial,
    restart_all,
)

app_name = "host_ui"

urlpatterns = [
    path("", host_page, name="host_page"),
    path("_vitals/", host_vitals_partial, name="host_vitals_partial"),
    path("container/<str:name>/restart/", container_restart, name="container_restart"),
    path("container/<str:name>/stop/", container_stop, name="container_stop"),
    path("container/<str:name>/start/", container_start, name="container_start"),
    path("restart-all/", restart_all, name="restart_all"),
]