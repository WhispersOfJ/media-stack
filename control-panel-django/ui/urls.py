from django.urls import path

from ui.views import (
    activity_log_page,
    activity_timeline_partial,
    home,
    log_strip_partial,
    log_stream_partial,
    logs_page,
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
    path("activity/", activity_log_page, name="activity_log"),
    path("logs/", logs_page, name="logs"),
    # htmx partial swap targets
    path("partials/log-strip/", log_strip_partial, name="log_strip_partial"),
    path("partials/status-dot/", status_dot_partial, name="status_dot_partial"),
    path("partials/overview-cards/", overview_cards_partial, name="overview_cards_partial"),
    path("partials/activity-timeline/", activity_timeline_partial, name="activity_timeline_partial"),
    path("partials/log-stream/", log_stream_partial, name="log_stream_partial"),
]