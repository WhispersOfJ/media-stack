from django.urls import path

from ui.views import (
    activity_log_page,
    home,
    log_strip_partial,
    overview_cards_partial,
    reference_page,
    settings_page,
    status_dot_partial,
)

app_name = "ui"

urlpatterns = [
    path("", home, name="home"),
    path("settings/", settings_page, name="settings"),
    path("reference/", reference_page, name="reference"),
    path("activity-log/", activity_log_page, name="activity_log"),
    # htmx partial swap targets
    path("partials/log-strip/", log_strip_partial, name="log_strip_partial"),
    path("partials/status-dot/", status_dot_partial, name="status_dot_partial"),
    path("partials/overview-cards/", overview_cards_partial, name="overview_cards_partial"),
]