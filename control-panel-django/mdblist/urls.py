from django.urls import path

from mdblist.views import mdblist_page

app_name = "mdblist_ui"

urlpatterns = [
    path("", mdblist_page, name="mdblist_page"),
]