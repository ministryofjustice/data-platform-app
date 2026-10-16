from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command

from support_assistant.exceptions import GuideFetchError
from support_assistant.guide import SyncResult


@pytest.mark.django_db
class TestSyncUserGuideCommand:
    def test_reports_result(self, capsys):
        with patch(
            "support_assistant.management.commands.sync_user_guide.sync_user_guide",
            return_value=SyncResult(files=2, created=3, updated=1, deleted=4),
        ):
            call_command("sync_user_guide")

        assert "Synced 2 file(s): 3 created, 1 updated, 4 deleted." in capsys.readouterr().out

    def test_raises_command_error_on_fetch_failure(self):
        with (
            patch(
                "support_assistant.management.commands.sync_user_guide.sync_user_guide",
                side_effect=GuideFetchError("GitHub returned 404"),
            ),
            pytest.raises(CommandError, match="404"),
        ):
            call_command("sync_user_guide")

    def test_raises_command_error_when_not_configured(self, settings):
        settings.SUPPORT_ASSISTANT_GUIDE_REPO = ""

        with pytest.raises(CommandError, match="SUPPORT_ASSISTANT_GUIDE_REPO"):
            call_command("sync_user_guide")

    def test_raises_command_error_when_base_url_missing(self):
        with (
            patch(
                "support_assistant.management.commands.sync_user_guide.sync_user_guide",
                side_effect=ImproperlyConfigured("SUPPORT_ASSISTANT_GUIDE_BASE_URL"),
            ),
            pytest.raises(CommandError, match="BASE_URL"),
        ):
            call_command("sync_user_guide")
