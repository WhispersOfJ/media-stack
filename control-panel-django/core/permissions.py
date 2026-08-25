from rest_framework.permissions import BasePermission


class IsAuthenticatedOrServiceKey(BasePermission):
    """Mirrors the FastAPI-era current_user_or_service dependency: a valid
    session OR a valid X-Api-Key both satisfy this permission. Views on
    mutating routes that must reject service keys (documented per-route in
    Phase 2, same discipline as the old services/*/router.py comments) use a
    stricter permission class instead of this one."""

    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_authenticated", False))


class IsAuthenticatedSessionOnly(BasePermission):
    """Stricter than IsAuthenticatedOrServiceKey: rejects the
    AnonymousServiceUser stand-in, so an X-Api-Key header alone cannot
    trigger admin/irreversible actions (host reboot, pacman, settings
    PATCH, disk-health prune, radarr exclude) — session cookie required."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and not getattr(user, "is_service_account", False)
        )


class IsAuthenticatedSessionOrBearer(BasePermission):
    """Allows either a session cookie OR a valid bearer token (Authorization:
    Bearer <key>) to access the view. Rejects X-Api-Key alone — those callers
    should use the bearer header instead for host-level actions. This is the
    permission class for /api/v2/host/* destructive endpoints."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not getattr(user, "is_authenticated", False):
            return False
        # Session users (not service accounts) always pass
        if not getattr(user, "is_service_account", False):
            return True
        # Service accounts only pass if authenticated via Bearer header
        # (AnonymousServiceUser from BearerTokenAuthentication)
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        return auth_header.startswith("Bearer ")
