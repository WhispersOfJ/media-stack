from django.urls import path

from posters.views import posters_gallery_partial, posters_page

app_name = "posters_ui"

urlpatterns = [
    path("", posters_page, name="posters_page"),
    path("_gallery/<str:library>/", posters_gallery_partial, name="posters_gallery_partial"),
]