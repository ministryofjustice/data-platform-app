from django.db import connection

from ai_gateway.models import Key

SECRET = "sk-super-secret-value-1234567890"


class TestEncryptedTextField:
    def test_value_through_the_orm(self, project, user):
        key = Key.objects.create(
            project=project,
            name="primary-key",
            litellm_secret=SECRET,
            litellm_alias="example-slug-primary-key-abcdef",
            litellm_token="tok-1",
            masked_key="sk-sup...7890",
            created_by=user,
        )

        assert Key.objects.get(pk=key.pk).litellm_secret == SECRET

    def test_value_is_encrypted_at_rest(self, project, user):
        key = Key.objects.create(
            project=project,
            name="primary-key",
            litellm_secret=SECRET,
            litellm_alias="example-slug-primary-key-abcdef",
            litellm_token="tok-1",
            masked_key="sk-sup...7890",
            created_by=user,
        )

        with connection.cursor() as cursor:
            cursor.execute("SELECT litellm_secret FROM ai_gateway_key WHERE id = %s", [key.pk])
            raw_value = cursor.fetchone()[0]

        assert raw_value != SECRET
        assert SECRET not in raw_value
