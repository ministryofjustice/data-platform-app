from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from projects.graph import EntraAuthenticationError, EntraRequestError


@pytest.fixture
def graph():
    """Patch the Graph client the view builds, yielding (from_request, client)."""
    with patch("projects.views.MicrosoftGraphClient.from_request") as from_request:
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        from_request.return_value = client
        yield from_request, client


def search_url():
    return reverse("projects:entra_user_search")


class TestEntraUserSearchView:
    """Tests for the EntraUserSearchView at '/projects/entra-users/search/'."""

    def test_requires_login(self, client):
        response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 302

    def test_short_query_returns_empty_without_calling_graph(self, client, user, graph):
        from_request, _ = graph
        client.force_login(user)

        response = client.get(search_url(), {"q": "mi"})

        assert response.status_code == 200
        assert response.json() == {"results": []}
        from_request.assert_not_called()

    def test_returns_serialised_matches(self, client, user, graph):
        _, graph_client = graph
        graph_client.search_users.return_value = [
            {
                "id": "id-1",
                "displayName": "Michael Example",
                "mail": "michael.example@justice.gov.uk",
                "userPrincipalName": "michael.upn@justice.gov.uk",
            }
        ]
        client.force_login(user)

        response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 200
        assert response.json() == {
            "results": [
                {
                    "id": "id-1",
                    "display_name": "Michael Example",
                    "email": "michael.example@justice.gov.uk",
                }
            ]
        }

    def test_email_comes_from_mail(self, client, user, graph):
        _, graph_client = graph
        graph_client.search_users.return_value = [
            {"id": "id-2", "displayName": "Mila Match", "mail": "mila.match@justice.gov.uk"}
        ]
        client.force_login(user)

        response = client.get(search_url(), {"q": "mila"})

        assert response.json()["results"][0]["email"] == "mila.match@justice.gov.uk"

    def test_email_is_normalised_to_lowercase(self, client, user, graph):
        _, graph_client = graph
        graph_client.search_users.return_value = [
            {"id": "id-4", "displayName": "Mixed Case", "mail": "Mixed.Case@Justice.GOV.uk"}
        ]
        client.force_login(user)

        response = client.get(search_url(), {"q": "mix"})

        assert response.json()["results"][0]["email"] == "mixed.case@justice.gov.uk"

    def test_does_not_leak_extra_graph_fields(self, client, user, graph):
        _, graph_client = graph
        graph_client.search_users.return_value = [
            {
                "id": "id-3",
                "displayName": "Jane Doe",
                "mail": "jane@justice.gov.uk",
                "jobTitle": "Secret",
                "officeLocation": "HQ",
            }
        ]
        client.force_login(user)

        response = client.get(search_url(), {"q": "jan"})

        assert set(response.json()["results"][0].keys()) == {"id", "display_name", "email"}

    def test_caps_query_length_before_searching(self, client, user, graph):
        _, graph_client = graph
        graph_client.search_users.return_value = []
        client.force_login(user)

        client.get(search_url(), {"q": "a" * 500})

        sent_query = graph_client.search_users.call_args.args[0]
        assert len(sent_query) == 256

    def test_missing_cached_token_returns_401(self, client, user, graph):
        from_request, _ = graph
        from_request.side_effect = EntraAuthenticationError("no token")
        client.force_login(user)

        response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 401
        assert response.json() == {"error": "authentication_required"}

    def test_graph_error_returns_502(self, client, user, graph):
        _, graph_client = graph
        graph_client.search_users.side_effect = EntraRequestError("boom")
        client.force_login(user)

        with patch("projects.views.sentry_sdk.capture_exception") as capture_exception:
            response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 502
        assert response.json() == {"error": "search_failed"}
        capture_exception.assert_called_once()
