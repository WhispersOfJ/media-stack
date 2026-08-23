from django.urls import path

from arr.views import (
    fleet_cards_partial,
    fleet_page,
    queue_autofix_action,
    queue_table_partial,
    unstick_action,
)

app_name = "arr_ui"

urlpatterns = [
    path("", fleet_page, name="fleet_page"),
    path("_cards/", fleet_cards_partial, name="fleet_cards_partial"),
    path("_queue/", queue_table_partial, name="queue_table_partial"),
    path("autofix/", queue_autofix_action, name="queue_autofix"),
    path("<str:app_name>/unstick/", unstick_action, name="unstick"),
]