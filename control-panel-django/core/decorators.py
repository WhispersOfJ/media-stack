"""Decorators for Django template views.

login_required: redirects to auth_app:login when request.session["user_id"]
    is missing. Template views use session auth only — never X-Api-Key.

session_only_action: raises PermissionDenied (403) if the request carries
    an X-Api-Key header or has no session user. Defense-in-depth for
    destructive POSTs (host settings PATCH, reboot, prune, arr
    manual-import/blocklist, posters destructive ops).
"""

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def login_required(view):
    """Template-view decorator: redirect to login if no session user_id."""

    def wrapper(request, *args, **kwargs):
        if not request.session.get("user_id"):
            return redirect("auth_app:login")
        return view(request, *args, **kwargs)

    # Preserve view metadata for URL resolution and test introspection.
    wrapper.__name__ = view.__name__
    wrapper.__module__ = view.__module__
    return wrapper


def session_only_action(view):
    """POST-only guard: reject X-Api-Key callers (403) — session required.

    Layered on top of login_required in the view stack.  This is the
    same logic as core.permissions.IsAuthenticatedSessionOnly, but for
    template views which don't go through DRF's permission classes.
    """

    def wrapper(request, *args, **kwargs):
        if request.META.get("HTTP_X_API_KEY"):
            raise PermissionDenied("UI actions require a browser session, not a service key.")
        if not request.session.get("user_id"):
            raise PermissionDenied("Session required for this action.")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__module__ = view.__module__
    return wrapper