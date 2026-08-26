from unittest.mock import patch

import httpx
import pytest
from django.urls import reverse


def graph_response(value, status=200):
    """Build an ``httpx.Response`` mimicking a Microsoft Graph ``/users`` reply."""
    request = httpx.Request("GET", "https://graph.microsoft.com/v1.0/users")
    body = {"value": value} if status == 200 else {"error": {"code": "Error"}}
    return httpx.Response(status, json=body, request=request)


@pytest.fixture
def token():
    """Patch the delegated token lookup to return a usable access token."""
    with patch("projects.views.AuthHandler") as mock_auth:
        mock_auth.return_value.get_token_from_cache.return_value = {"access_token": "tok"}
        yield mock_auth


def search_url():
    return reverse("projects:entra_user_search")


class TestEntraUserSearchView:
    """Tests for the EntraUserSearchView at '/projects/entra-users/search/'."""

    def test_requires_login(self, client):
        response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 302

    def test_short_query_returns_empty_without_calling_graph(self, client, user, token):
        client.force_login(user)

        with patch("projects.views.httpx.get") as mock_get:
            response = client.get(search_url(), {"q": "mi"})

        assert response.status_code == 200
        assert response.json() == {"results": []}
        mock_get.assert_not_called()

    def test_returns_serialised_matches(self, client, user, token):
        client.force_login(user)
        value = [
            {
                "id": "id-1",
                "displayName": "Michael Example",
                "mail": "michael.example@justice.gov.uk",
                "userPrincipalName": "michael.upn@justice.gov.uk",
            }
        ]

        with patch("projects.views.httpx.get", return_value=graph_response(value)):
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

    def test_email_comes_from_mail(self, client, user, token):
        client.force_login(user)
        value = [
            {
                "id": "id-2",
                "displayName": "Mila Match",
                "mail": "mila.match@justice.gov.uk",
            }
        ]

        with patch("projects.views.httpx.get", return_value=graph_response(value)):
            response = client.get(search_url(), {"q": "mila"})

        assert response.json()["results"][0]["email"] == "mila.match@justice.gov.uk"

    def test_does_not_leak_extra_graph_fields(self, client, user, token):
        client.force_login(user)
        value = [
            {
                "id": "id-3",
                "displayName": "Jane Doe",
                "mail": "jane@justice.gov.uk",
                "userPrincipalName": "jane@justice.gov.uk",
                "jobTitle": "Secret",
                "officeLocation": "HQ",
            }
        ]

        with patch("projects.views.httpx.get", return_value=graph_response(value)):
            response = client.get(search_url(), {"q": "jan"})

        assert set(response.json()["results"][0].keys()) == {"id", "display_name", "email"}

    def test_requests_expected_select_and_top(self, client, user, token):
        client.force_login(user)

        with patch("projects.views.httpx.get", return_value=graph_response([])) as mock_get:
            client.get(search_url(), {"q": "mic"})

        params = mock_get.call_args.kwargs["params"]
        assert params["$select"] == "id,displayName,mail"
        assert params["$top"] == "10"
        assert params["$filter"] == "startsWith(mail,'mic')"

    def test_escapes_single_quotes_in_query(self, client, user, token):
        client.force_login(user)

        with patch("projects.views.httpx.get", return_value=graph_response([])) as mock_get:
            client.get(search_url(), {"q": "O'Brien"})

        assert "O''Brien" in mock_get.call_args.kwargs["params"]["$filter"]

    def test_does_not_send_bearer_token_to_browser(self, client, user, token):
        client.force_login(user)

        with patch("projects.views.httpx.get", return_value=graph_response([])):
            response = client.get(search_url(), {"q": "mic"})

        assert "tok" not in response.content.decode()

    def test_missing_cached_token_returns_401(self, client, user):
        client.force_login(user)

        with patch("projects.views.AuthHandler") as mock_auth:
            mock_auth.return_value.get_token_from_cache.return_value = None
            response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 401
        assert response.json() == {"error": "authentication_required"}

    def test_token_without_access_token_returns_401(self, client, user):
        client.force_login(user)

        with patch("projects.views.AuthHandler") as mock_auth:
            mock_auth.return_value.get_token_from_cache.return_value = {}
            response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 401

    @pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
    def test_graph_error_returns_502(self, client, user, token, status):
        client.force_login(user)

        with patch("projects.views.httpx.get", return_value=graph_response([], status=status)):
            response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 502
        assert response.json() == {"error": "search_failed"}

    def test_graph_timeout_returns_502(self, client, user, token):
        client.force_login(user)

        with patch("projects.views.httpx.get", side_effect=httpx.TimeoutException("timed out")):
            response = client.get(search_url(), {"q": "mic"})

        assert response.status_code == 502
