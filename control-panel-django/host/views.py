"""Host page — container grid, vitals, resource/mount/disk health, actions.

Template views call host.services directly server-side.  Destructive
actions (settings PATCH, reboot, prune) require the session tier via
the @session_only_action decorator (layered on @login_required).
"""

from django.shortcuts import render

from core.decorators import login_required, session_only_action
from host import services


@login_required
def host_page(request):
    """Full host status page: container grid + vitals + resources + mounts."""
    try:
        containers = services.list_containers()
    except Exception:
        containers = []
    try:
        hr = services.host_resources()
    except Exception:
        hr = {}
    try:
        disk = services.disk_health()
    except Exception:
        disk = {}
    try:
        mounts = services.mount_health()
    except Exception:
        mounts = {}

    return render(
        request,
        "host/host.html",
        {
            "page": "host",
            "containers": containers,
            "cpu_percent": hr.get("cpu_percent"),
            "mem_percent": hr.get("mem_percent"),
            "mem_used": hr.get("mem_used"),
            "mem_total": hr.get("mem_total"),
            "disk": disk,
            "mounts": mounts.get("mounts", []),
        },
    )


@login_required
def host_vitals_partial(request):
    """htmx swap target: containers + vitals fragment."""
    try:
        containers = services.list_containers()
    except Exception:
        containers = []
    return render(request, "host/partials/_containers.html", {"containers": containers})


@login_required
def container_restart(request, name):
    services.restart_container(name)
    return host_vitals_partial(request)


@login_required
def container_stop(request, name):
    services.stop_container(name)
    return host_vitals_partial(request)


@login_required
def container_start(request, name):
    services.start_container(name)
    return host_vitals_partial(request)


@login_required
def restart_all(request):
    services.restart_all()
    return host_vitals_partial(request)