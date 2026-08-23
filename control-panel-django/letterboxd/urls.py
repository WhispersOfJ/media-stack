from django.urls import path

from letterboxd.views import letterboxd_page

app_name = "letterboxd_ui"

urlpatterns = [
    path("", letterboxd_page, name="letterboxd_page"),
]