import pytest


@pytest.fixture
def anonymous_user(db):
    """An unsaved AnonymousUser instance."""
    from django.contrib.auth.models import AnonymousUser

    return AnonymousUser()


@pytest.fixture
def user(db):
    """A saved User instance with no special permissions."""
    from model_bakery import baker

    return baker.make("users.User")
