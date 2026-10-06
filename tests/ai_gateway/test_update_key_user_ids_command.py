from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from model_bakery import baker

from ai_gateway.exceptions import AIGatewayAPIError


@patch("ai_gateway.management.commands.update_key_user_ids.AIGatewayClient.from_settings")
def test_updates_creator_ids_and_skips_keys_without_creator(from_settings, key, project, user):
    gateway_client = from_settings.return_value
    baker.make(
        "ai_gateway.Key",
        project=project,
        name="unowned-key",
        litellm_alias="unowned-key-alias",
        litellm_secret="sk-unused",
        created_by=None,
    )
    output = StringIO()

    call_command("update_key_user_ids", stdout=output)

    gateway_client.update_key_user_id.assert_called_once_with(key.litellm_token, str(user.oid))
    gateway_client.close.assert_called_once()
    assert output.getvalue() == (
        "Updated 1 key(s); skipped 1 key(s) without a creator; failed 0 key(s).\n"
    )


@patch("ai_gateway.management.commands.update_key_user_ids.AIGatewayClient.from_settings")
def test_dry_run_does_not_create_client_or_call_gateway(from_settings, key):
    output = StringIO()

    call_command("update_key_user_ids", "--dry-run", stdout=output)

    from_settings.assert_not_called()
    assert output.getvalue() == (
        "Dry run: 1 key(s) would be updated; 0 key(s) without a creator would be skipped.\n"
    )


@patch("ai_gateway.management.commands.update_key_user_ids.AIGatewayClient.from_settings")
def test_continues_after_gateway_error_then_fails_command(from_settings, key, project, user):
    gateway_client = from_settings.return_value
    second_key = baker.make(
        "ai_gateway.Key",
        project=project,
        name="secondary-key",
        litellm_alias="second-key-alias",
        litellm_secret="sk-second",
        created_by=user,
    )
    gateway_client.update_key_user_id.side_effect = [
        AIGatewayAPIError(500, "gateway unavailable"),
        None,
    ]
    output = StringIO()
    errors = StringIO()

    with pytest.raises(CommandError, match="Failed to update 1 of 2"):
        call_command("update_key_user_ids", stdout=output, stderr=errors)

    assert gateway_client.update_key_user_id.call_count == 2
    gateway_client.close.assert_called_once()
    assert str(key.pk) in errors.getvalue()
    assert "Updated 1 key(s)" in output.getvalue()
    assert "failed 1 key(s)" in output.getvalue()
    assert second_key.pk != key.pk
