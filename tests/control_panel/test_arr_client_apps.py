"""Gate tests for the sonarr_anime app entry added alongside radarr_anime
in core/arr_client.py - closes the same "app_name == 'radarr'" trap radarr_anime
had (queue items silently treated as the wrong shape) for the Sonarr side."""
import sys


def test_sonarr_anime_present_in_arr_apps(cp_main_app):
    arr_client = sys.modules["core.arr_client"]
    assert "sonarr_anime" in arr_client.ARR_APPS
    entry = arr_client.ARR_APPS["sonarr_anime"]
    assert entry["url"] == "http://sonarr-anime:8989"
    assert entry["search_command"] == "MissingEpisodeSearch"


def test_sonarr_anime_in_queue_arr_apps(cp_main_app):
    arr_client = sys.modules["core.arr_client"]
    assert "sonarr_anime" in arr_client.QUEUE_ARR_APPS


def test_sonarr_anime_is_not_radarr_shaped(cp_main_app):
    # sonarr_anime is a second Sonarr instance (episodes, episodeId) - it must
    # NOT be in RADARR_APPS, or its queue items get the movie-shaped id field
    # and search command (the exact bug radarr_anime's own addition guarded
    # against on the Radarr side).
    arr_client = sys.modules["core.arr_client"]
    assert "sonarr_anime" not in arr_client.RADARR_APPS
    assert "radarr_anime" in arr_client.RADARR_APPS


def test_docker_client_has_sonarr_anime_label(cp_main_app):
    docker_client = sys.modules["core.docker_client"]
    assert "sonarr-anime" in docker_client.CONTAINER_LABELS
