import os

import pytest

from core.api_base import ServiceError
from ratings.services import get_imdb_rating, get_mdblist_rating


def test_get_imdb_rating_success(httpx_mock, monkeypatch):
    monkeypatch.setenv("OMDB_KEY", "test-key")
    httpx_mock.add_response(
        url="https://www.omdbapi.com/?apikey=test-key&i=tt0111161",
        json={"Title": "The Shawshank Redemption", "Year": "1994", "imdbRating": "9.3", "imdbVotes": "2,900,000", "Response": "True"},
    )
    result = get_imdb_rating("tt0111161")
    assert result["title"] == "The Shawshank Redemption"
    assert result["rating"] == "9.3"


def test_get_imdb_rating_no_omdb_key_raises(monkeypatch):
    monkeypatch.delenv("OMDB_KEY", raising=False)
    with pytest.raises(ServiceError):
        get_imdb_rating("tt0111161")


def test_get_imdb_rating_no_match_raises_404(httpx_mock, monkeypatch):
    monkeypatch.setenv("OMDB_KEY", "test-key")
    httpx_mock.add_response(json={"Response": "False", "Error": "Movie not found!"})
    with pytest.raises(ServiceError) as exc_info:
        get_imdb_rating("tt0000000")
    assert exc_info.value.status_code == 404


def test_get_mdblist_rating_success(httpx_mock, monkeypatch):
    monkeypatch.setenv("MDBLIST_KEY", "test-key")
    httpx_mock.add_response(
        url="https://mdblist.com/api/?apikey=test-key&i=tt0111161",
        json={"title": "The Shawshank Redemption", "year": "1994", "score": 90, "imdbrating": "9.3", "imdbvotes": "2900000"},
    )
    result = get_mdblist_rating("tt0111161")
    assert result["title"] == "The Shawshank Redemption"
    assert result["score"] == 90


def test_get_mdblist_rating_no_mdblist_key_raises(monkeypatch):
    monkeypatch.delenv("MDBLIST_KEY", raising=False)
    with pytest.raises(ServiceError):
        get_mdblist_rating("tt0111161")


def test_get_mdblist_rating_no_votes_raises_404(httpx_mock, monkeypatch):
    monkeypatch.setenv("MDBLIST_KEY", "test-key")
    httpx_mock.add_response(json={"title": None, "imdbvotes": 0})
    with pytest.raises(ServiceError) as exc_info:
        get_mdblist_rating("tt0000000")
    assert exc_info.value.status_code == 404
