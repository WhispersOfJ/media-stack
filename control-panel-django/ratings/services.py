import os

import httpx

from core.api_base import ServiceError


def get_imdb_rating(imdb_id: str) -> dict:
    api_key = os.environ.get("OMDB_KEY")
    if not api_key:
        raise ServiceError("OMDB_KEY is not configured", status=500)
    response = httpx.get("https://www.omdbapi.com/", params={"apikey": api_key, "i": imdb_id}, timeout=10)
    data = response.json()
    if data.get("Response") != "True":
        raise ServiceError(data.get("Error", "No match found"), status=404)
    return {
        "imdbId": imdb_id,
        "title": data.get("Title"),
        "year": data.get("Year"),
        "rating": data.get("imdbRating"),
        "votes": data.get("imdbVotes"),
    }


def get_mdblist_rating(imdb_id: str) -> dict:
    api_key = os.environ.get("MDBLIST_KEY")
    if not api_key:
        raise ServiceError("MDBLIST_KEY is not configured", status=500)
    response = httpx.get("https://mdblist.com/api/", params={"apikey": api_key, "i": imdb_id}, timeout=10)
    data = response.json()
    imdb_votes = data.get("imdbvotes") or 0
    if not data.get("title") or int(imdb_votes) <= 0:
        raise ServiceError("No reliable rating found", status=404)
    return {
        "imdbId": imdb_id,
        "title": data.get("title"),
        "year": data.get("year"),
        "score": data.get("score"),
        "imdbRating": data.get("imdbrating"),
        "imdbVotes": imdb_votes,
    }
