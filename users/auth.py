"""User attribute mapping for Microsoft Entra ID authentication."""

from typing import Any


def user_mapping_fn(**attributes: Any) -> dict[str, str]:
    """Map Microsoft Entra ID attributes to Django user model fields.

    Called by ``django-azure-auth`` when creating or updating a user after a
    successful login. Users are identified by the immutable Entra object id
    (``oid``), so this mapping keeps the mutable email and name fields in sync
    on every login without changing the user's identity or creating duplicates.

    Only attributes present in the token/profile are returned, so a missing
    claim never overwrites an existing value with empty data.

    ``oid`` is intentionally omitted because ``django-azure-auth`` supplies it
    separately as the user's login identity via ``USERNAME_ATTRIBUTE`` /
    ``USERNAME_FIELD``.
    """
    field_by_attribute = {
        "mail": "email",
        "givenName": "first_name",
        "surname": "last_name",
        "displayName": "username",
    }
    mapped_fields = {
        field: attributes[attribute]
        for attribute, field in field_by_attribute.items()
        if attributes.get(attribute)
    }
    if email := mapped_fields.get("email"):
        mapped_fields["email"] = email.lower()
    return mapped_fields
