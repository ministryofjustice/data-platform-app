from users.auth import user_mapping_fn


class TestUserMappingFn:
    """Tests for mapping Entra ID attributes to Django user fields."""

    def test_maps_all_supported_attributes(self):
        mapped = user_mapping_fn(
            oid="00000000-0000-0000-0000-000000000000",
            mail="jane.doe@example.com",
            givenName="Jane",
            surname="Doe",
            displayName="Jane Doe",
        )

        assert mapped == {
            "email": "jane.doe@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "username": "Jane Doe",
        }

    def test_lowercases_email(self):
        mapped = user_mapping_fn(oid="abc", mail="Jane.Doe@Example.COM")

        assert mapped == {"email": "jane.doe@example.com"}

    def test_ignores_unmapped_attributes(self):
        mapped = user_mapping_fn(
            oid="abc",
            mail="jane.doe@example.com",
            jobTitle="Analyst",
        )

        assert mapped == {"email": "jane.doe@example.com"}

    def test_omits_missing_or_empty_claims(self):
        mapped = user_mapping_fn(mail="jane.doe@example.com", givenName="", surname=None)

        assert mapped == {"email": "jane.doe@example.com"}

    def test_returns_empty_when_no_mappable_attributes(self):
        assert user_mapping_fn(oid="abc") == {}
