"""Host/fleet routes - status, container management, settings, diagnostics.
Ported from control-panel/services/host/router.py.

Auth split, matching the FastAPI-era source exactly:
- patch_settings (PATCH /api/v2/host/settings) and prune_disk
  (POST /api/v2/host/disk-health/prune) are IsAuthenticatedSessionOnly
  (admin, session-cookie-only) - the only two current_user-tier routes in
  the source's 24.
- Every other route is the default EnvelopeAPIView tier
  (IsAuthenticatedOrServiceKey) - the FastAPI-era current_user_or_service
  dependency, including the mutating container routes (restart/stop/start,
  restart-all), which stack-container.fish/stack-restart-all.fish call
  unattended via __stack_api's service key.

The container-logs stream view is NOT an EnvelopeAPIView (SSE isn't a JSON
envelope response) - it reuses posters.api.sse.sse_response, the same
helper the posters app's three stream views use, and picks up the default
auth pair from REST_FRAMEWORK settings like the posters stream views do.
"""
from rest_framework.views import APIView

from core.api_base import EnvelopeAPIView, ServiceError
from core.permissions import IsAuthenticatedOrServiceKey, IsAuthenticatedSessionOnly
from host import services
from host.api.serializers import (
    LogsStreamQuerySerializer,
    PruneRequestSerializer,
    RestartQuerySerializer,
    SettingsPatchSerializer,
    TopQuerySerializer,
)


def sse_response(generator):
    """Create an SSE StreamingHttpResponse from a generator."""
    from django.http import StreamingHttpResponse
    response = StreamingHttpResponse(generator, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class StatusView(EnvelopeAPIView):
    """GET /api/v2/host/status - every container's state + health."""

    def get(self, request):
        result = services.get_status()
        return self.ok(f"{len(result)} container(s).", containers=result)


class ContainersView(EnvelopeAPIView):
    """GET /api/v2/host/containers - full container grid with stats."""

    def get(self, request):
        items = services.list_containers()
        return self.ok(f"{len(items)} container(s).", items=items)


class ContainerRestartView(EnvelopeAPIView):
    """POST /api/v2/host/container/<name>/restart?activated=..."""

    def post(self, request, name):
        query = RestartQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        message = services.restart_container(name, query.validated_data["activated"])
        return self.ok(message)


class ContainerStopView(EnvelopeAPIView):
    """POST /api/v2/host/container/<name>/stop"""

    def post(self, request, name):
        message = services.stop_container(name)
        return self.ok(message)


class ContainerStartView(EnvelopeAPIView):
    """POST /api/v2/host/container/<name>/start"""

    def post(self, request, name):
        message = services.start_container(name)
        return self.ok(message)


class ContainerLogsStreamView(APIView):
    """GET /api/v2/host/container/<name>/logs/stream?tail=..."""

    def get(self, request, name):
        query = LogsStreamQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        generator = services.stream_container_logs(name, query.validated_data["tail"])
        return sse_response(generator)


class RestartAllView(EnvelopeAPIView):
    """POST /api/v2/host/stack/restart-all"""

    def post(self, request):
        message = services.restart_all()
        return self.ok(message)


class SettingsView(EnvelopeAPIView):
    """GET /api/v2/host/settings - every saved setting (default tier).

    PATCH /api/v2/host/settings - update settings; session-only (admin
    action, the FastAPI-era current_user dependency). The two methods
    share one URL, so the permission split is per-method rather than
    per-view: get_permissions() returns IsAuthenticatedSessionOnly for
    PATCH and the default pair for GET."""

    def get_permissions(self):
        if self.request and self.request.method == "PATCH":
            return [IsAuthenticatedSessionOnly()]
        return [IsAuthenticatedOrServiceKey()]

    def get(self, request):
        result = services.get_settings()
        return self.ok("Settings fetched.", **result)

    def patch(self, request):
        body = SettingsPatchSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        patch = {k: v for k, v in body.validated_data.items() if v is not None}
        result = services.patch_settings(patch)
        return self.ok("Settings updated.", **result)


class ResourceCheckView(EnvelopeAPIView):
    """GET /api/v2/host/resource-check"""

    def get(self, request):
        result = services.resource_check()
        message = result.pop("message")
        return self.ok(message, **result)


class DiskHealthView(EnvelopeAPIView):
    """GET /api/v2/host/disk-health"""

    def get(self, request):
        result = services.disk_health()
        message = result.pop("message")
        return self.ok(message, **result)


class PruneDiskView(EnvelopeAPIView):
    """POST /api/v2/host/disk-health/prune - session-only (admin action),
    requires confirm=true in the body (checked before services is called,
    matching the FastAPI-era router's payload.confirm gate)."""

    permission_classes = [IsAuthenticatedSessionOnly]

    def post(self, request):
        body = PruneRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if not body.validated_data["confirm"]:
            raise ServiceError(
                "Set confirm=true to prune - this deletes dangling images and unused volumes.",
                status=400,
            )
        message = services.prune_disk()
        return self.ok(message)


class HostResourcesView(EnvelopeAPIView):
    """GET /api/v2/host/host-resources"""

    def get(self, request):
        result = services.host_resources()
        message = result.pop("message")
        return self.ok(message, **result)


class LogLevelsView(EnvelopeAPIView):
    """GET /api/v2/host/log-levels"""

    def get(self, request):
        result = services.log_levels()
        message = result.pop("message")
        return self.ok(message, **result)


class ResetLogLevelsView(EnvelopeAPIView):
    """POST /api/v2/host/log-levels/reset

    Resets all debug-logging apps back to info level. Uses the default
    IsAuthenticatedOrServiceKey permission (not session-only) — this is a
    maintenance action, not irreversible like host reboot."""

    def post(self, request):
        message = services.reset_log_levels()
        return self.ok(message)


class OomCheckView(EnvelopeAPIView):
    """GET /api/v2/host/oom-check"""

    def get(self, request):
        result = services.oom_check()
        message = result.pop("message")
        return self.ok(message, **result)


class DiskUsageView(EnvelopeAPIView):
    """GET /api/v2/host/disk-usage"""

    def get(self, request):
        result = services.disk_usage()
        message = result.pop("message")
        return self.ok(message, **result)


class MountHealthView(EnvelopeAPIView):
    """GET /api/v2/host/mount-health"""

    def get(self, request):
        result = services.mount_health()
        message = result.pop("message")
        return self.ok(message, **result)


class PermsCheckView(EnvelopeAPIView):
    """GET /api/v2/host/perms-check"""

    def get(self, request):
        result = services.perms_check()
        message = result.pop("message")
        return self.ok(message, **result)


class ImageCheckView(EnvelopeAPIView):
    """GET /api/v2/host/image-check"""

    def get(self, request):
        result = services.image_check()
        message = result.pop("message")
        return self.ok(message, **result)


class VersionView(EnvelopeAPIView):
    """GET /api/v2/host/version"""

    def get(self, request):
        result = services.get_version()
        message = result.pop("message")
        return self.ok(message, **result)


class DocsReadmeView(EnvelopeAPIView):
    """GET /api/v2/host/docs/readme"""

    def get(self, request):
        text = services.docs_readme()
        return self.ok("README.md", text=text)


class NotifyTestView(EnvelopeAPIView):
    """POST /api/v2/host/notify/test

    Sends a test notification to the configured Discord webhook. Uses the
    default IsAuthenticatedOrServiceKey permission (not session-only) —
    harmless, idempotent, useful for automation health checks."""

    def post(self, request):
        message = services.notify_test()
        return self.ok(message)


class TopView(EnvelopeAPIView):
    """GET /api/v2/host/top?by=cpu|mem&limit=..."""

    def get(self, request):
        query = TopQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = services.stack_top(query.validated_data["by"], query.validated_data["limit"])
        message = result.pop("message")
        return self.ok(message, **result)


class HealthCheckView(EnvelopeAPIView):
    """GET /api/v2/host/health - check all service health endpoints.

    Returns a dict mapping service name to {status: "up"|"down", code: int}.
    Uses the same API keys the control panel already has for Arr/NzbDAV.
    The landing page calls this instead of hitting each service directly.
    Public endpoint (no auth) so the landing page can poll it.
    """

    permission_classes = []  # AllowAny - read-only status check

    def get(self, request):
        import concurrent.futures
        import httpx

        from core.arr_client import ARR_APPS, PROWLARR_CFG
        from core.nzbdav_client import NZBDAV_API_KEY, NZBDAV_URL

        services_to_check = [
            {"name": "Plex", "url": "http://plex:32400/identity", "timeout": 3},
            {"name": "Radarr", "url": f"{ARR_APPS['radarr']['url']}/api/v3/system/status", "headers": {"X-Api-Key": ARR_APPS['radarr']['key']}, "timeout": 3},
            {"name": "Sonarr", "url": f"{ARR_APPS['sonarr']['url']}/api/v3/system/status", "headers": {"X-Api-Key": ARR_APPS['sonarr']['key']}, "timeout": 3},
            {"name": "Prowlarr", "url": f"{PROWLARR_CFG['url']}/api/v1/system/status", "headers": {"X-Api-Key": PROWLARR_CFG['key']}, "timeout": 3},
            {"name": "NzbDAV", "url": f"{NZBDAV_URL}/api?mode=get_cats&output=json", "headers": {"apikey": NZBDAV_API_KEY}, "timeout": 3},
            {"name": "Overseerr", "url": "http://seerr:5055/api/v1/status", "timeout": 3},
            {"name": "Control Panel", "url": "http://localhost:8420/healthz", "timeout": 2},
            {"name": "Metacache", "url": "http://metacache:8765/healthz", "timeout": 2},
            {"name": "Watchstate", "url": "http://watchstate:8080/", "timeout": 3},
            {"name": "Cleanuparr", "url": "http://cleanuparr:11011/health", "timeout": 2},
            {"name": "Grafana", "url": "http://grafana:3000/api/health", "timeout": 2},
            {"name": "Prometheus", "url": "http://prometheus:9090/-/healthy", "timeout": 2},
        ]

        def check_one(svc):
            try:
                with httpx.Client(timeout=svc["timeout"], follow_redirects=True) as client:
                    r = client.get(svc["url"], headers=svc.get("headers", {}))
                    return svc["name"], {"status": "up" if r.status_code < 400 else "down", "code": r.status_code}
            except Exception:
                return svc["name"], {"status": "down", "code": 0}

        result = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for name, info in pool.map(check_one, services_to_check):
                result[name] = info

        response = self.ok(f"{sum(1 for v in result.values() if v['status'] == 'up')}/{len(result)} services up", services=result)
        response["Access-Control-Allow-Origin"] = "*"
        return response
