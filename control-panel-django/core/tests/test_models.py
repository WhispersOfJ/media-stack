import pytest

from core.models import User


@pytest.mark.django_db
def test_user_table_name_matches_existing_schema():
    assert User._meta.db_table == "users"


@pytest.mark.django_db
def test_user_defaults():
    user = User.objects.create(username="bear", password_hash="argon2-hash-placeholder")
    assert user.is_admin is True
    assert user.created_at is not None
