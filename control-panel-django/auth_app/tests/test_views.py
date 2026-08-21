import pytest
from django.test import Client
from django.urls import reverse

from core.models import User


@pytest.mark.django_db
def test_login_with_correct_credentials_sets_session():
    user = User(username="bear")
    user.set_password("hunter2")
    user.save()

    client = Client()
    response = client.post(
        reverse("auth_app:login"), {"username": "bear", "password": "hunter2"}, HTTP_HOST="localhost"
    )

    assert response.status_code == 302
    assert client.session["user_id"] == user.id


@pytest.mark.django_db
def test_login_with_wrong_password_shows_error():
    user = User(username="bear")
    user.set_password("hunter2")
    user.save()

    client = Client()
    response = client.post(
        reverse("auth_app:login"), {"username": "bear", "password": "wrong"}, HTTP_HOST="localhost"
    )

    assert response.status_code == 200
    assert "user_id" not in client.session
    assert b"Invalid username or password" in response.content


@pytest.mark.django_db
def test_login_with_unknown_username_shows_error():
    client = Client()
    response = client.post(reverse("auth_app:login"), {"username": "ghost", "password": "x"}, HTTP_HOST="localhost")

    assert response.status_code == 200
    assert b"Invalid username or password" in response.content


@pytest.mark.django_db
def test_logout_clears_session():
    user = User(username="bear")
    user.set_password("hunter2")
    user.save()

    client = Client()
    client.post(reverse("auth_app:login"), {"username": "bear", "password": "hunter2"}, HTTP_HOST="localhost")
    assert client.session["user_id"] == user.id

    response = client.post(reverse("auth_app:logout"), HTTP_HOST="localhost")
    assert response.status_code == 302
    assert "user_id" not in client.session


@pytest.mark.django_db
def test_login_page_renders():
    client = Client()
    response = client.get(reverse("auth_app:login"))
    assert response.status_code == 200
    assert b"<form" in response.content
