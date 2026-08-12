"""Canonical Organizr tab table for this stack - Phase 3 of PLANS.md.

Single source of truth, imported by BOTH this service's router (for the
/api/organizr/tabs/sync route) and the host-side bootstrap script
(scripts/organizr-provision.py). Adding a service to the stack means
adding one row here, nowhere else.

Two things in this table are load-bearing and were measured, not guessed:

1. `tab_type`. Organizr's own values are 0=Organizr-internal, 1=iFrame,
   2=New Window (js/functions.js:4628-4641). PLANS.md 3.4 asked for a
   per-service `X-Frame-Options`/CSP check before enabling iframe mode;
   that sweep ran against every live service on 2026-08-12 and exactly one
   service refuses framing - nzbdav sends `X-Frame-Options: SAMEORIGIN` on
   both its 302 and its final 200. Everything else in the stack, Plex's
   /web included, sends no framing headers at all. So nzbdav is the single
   TYPE_NEW_WINDOW row and the rest are iframes. test_organizr_router.py
   asserts exactly that, so the sweep result is encoded rather than folklore.

2. The URL host. These URLs are loaded by the *browser*, not by Organizr's
   PHP, so they must use the host IP - stacknet service names like
   `http://radarr:7878` resolve inside the compose network and nowhere else.

Icons: Organizr's `image` column accepts either a path into its bundled
icon set or a `<pack>::<name>` token that iconPrefix() (js/functions.js:555)
expands - `fontawesome::bell` becomes `<i class="fa fa-bell">`. The bundled
set has no icon for nzbdav/cleanuparr/maintainerr/lingarr/wrapperr/
ntfy/control-panel, so those use FontAwesome 4 names (the version Organizr
ships) instead of shipping our own image files into its volume.
"""

TYPE_ORGANIZR = 0
TYPE_IFRAME = 1
TYPE_NEW_WINDOW = 2

# Admin-only. Organizr group levels count *down* to more privilege
# (qualifyRequest passes when userLevel <= needed), so 0 is Admin. This is a
# single-operator stack with no guest accounts; every tab is admin-scoped.
ADMIN_GROUP_ID = 0

_BUNDLED = "plugins/images/tabs/"

# (name, port, path, image, tab_type)
TABS: list[dict] = [
    {"name": "Plex", "port": 32400, "path": "/web/index.html", "image": f"{_BUNDLED}plex.png", "tab_type": TYPE_IFRAME},
    {"name": "Seerr", "port": 5055, "path": "/", "image": f"{_BUNDLED}overseerr.png", "tab_type": TYPE_IFRAME},
    {"name": "Radarr", "port": 7878, "path": "/", "image": f"{_BUNDLED}radarr.png", "tab_type": TYPE_IFRAME},
    {"name": "Radarr Anime", "port": 7879, "path": "/", "image": f"{_BUNDLED}radarr.png", "tab_type": TYPE_IFRAME},
    {"name": "Sonarr", "port": 8989, "path": "/", "image": f"{_BUNDLED}sonarr.png", "tab_type": TYPE_IFRAME},
    {"name": "Sonarr Anime", "port": 8990, "path": "/", "image": f"{_BUNDLED}sonarr.png", "tab_type": TYPE_IFRAME},
    {"name": "Prowlarr", "port": 9696, "path": "/", "image": f"{_BUNDLED}prowlarr.png", "tab_type": TYPE_IFRAME},
    {"name": "Bazarr", "port": 6767, "path": "/", "image": f"{_BUNDLED}bazarr.png", "tab_type": TYPE_IFRAME},
    # The one framing refusal in the whole stack - see the module docstring.
    {"name": "NzbDAV", "port": 3000, "path": "/", "image": "fontawesome::cloud-download", "tab_type": TYPE_NEW_WINDOW},
    {"name": "Cleanuparr", "port": 11011, "path": "/", "image": "fontawesome::eraser", "tab_type": TYPE_IFRAME},
    {"name": "Maintainerr", "port": 6246, "path": "/", "image": "fontawesome::wrench", "tab_type": TYPE_IFRAME},
    {"name": "Lingarr", "port": 9876, "path": "/", "image": "fontawesome::language", "tab_type": TYPE_IFRAME},
    {"name": "Tautulli", "port": 8182, "path": "/", "image": f"{_BUNDLED}tautulli.png", "tab_type": TYPE_IFRAME},
    {"name": "Wrapperr", "port": 8283, "path": "/", "image": "fontawesome::gift", "tab_type": TYPE_IFRAME},
    {"name": "ntfy", "port": 8700, "path": "/", "image": "fontawesome::bell", "tab_type": TYPE_IFRAME},
    {"name": "Speedtest Tracker", "port": 8701, "path": "/", "image": f"{_BUNDLED}speedtest-icon.png", "tab_type": TYPE_IFRAME},
    {"name": "Control Panel", "port": 8420, "path": "/", "image": "fontawesome::sliders", "tab_type": TYPE_IFRAME},
]

# Deliberately absent, so a future session doesn't "notice the gap" and add
# them: kometa, unpackerr, watchtower, prefetcharr and nzbdav_rclone publish
# no port and have no web UI, and organizr does not get a tab pointing at
# itself.
NO_WEB_UI = ("kometa", "unpackerr", "watchtower", "prefetcharr", "nzbdav_rclone")


def tab_payload(tab: dict, host_ip: str) -> dict:
    """One tab row as Organizr's POST /api/v2/tabs expects it.

    addTab (api/classes/organizr.class.php:5389) requires `name`, `image`,
    and at least one of `url`/`url_local`, then drops any key that is not a
    real `tabs` column via checkKeys(). `order` is deliberately omitted so
    Organizr assigns getNextTabOrder()+1 and tabs land in this list's order.
    """
    url = f"http://{host_ip}:{tab['port']}{tab['path']}"
    return {
        "name": tab["name"],
        "url": url,
        "url_local": url,
        "image": tab["image"],
        "type": tab["tab_type"],
        "enabled": 1,
        "default": 0,
        "group_id": ADMIN_GROUP_ID,
    }
