from rest_framework.permissions import BasePermission


class IsAuthenticatedOrServiceKey(BasePermission):
    """Mirrors the FastAPI-era current_user_or_service dependency: a valid
    session OR a valid X-Api-Key both satisfy this permission. Views on
    mutating routes that must reject service keys (documented per-route in
    Phase 2, same discipline as the old services/*/router.py comments) use a
    stricter permission class instead of this one."""

    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_authenticated", False))
