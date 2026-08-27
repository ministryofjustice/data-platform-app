from unittest.mock import patch

import httpx
import pytest

from projects.graph import (
    EntraAuthenticationError,
    EntraRequestError,
    MicrosoftGraphClient,
)


def make_client(handler):
    """Build a ``MicrosoftGraphClient`` backed by a mock transport."""
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(base_url=MicrosoftGraphClient.BASE_URL, transport=transport)
    return MicrosoftGraphClient("tok", client=http_client)


class TestFromRequest:
    def test_builds_client_from_cached_token(self):
        with patch("projects.graph.AuthHandler") as mock_auth:
            mock_auth.return_value.get_token_from_cache.return_value = {"access_token": "tok"}
            client = MicrosoftGraphClient.from_request(request=object())

        assert isinstance(client, MicrosoftGraphClient)

    def test_raises_when_no_token_cached(self):
        with patch("projects.graph.AuthHandler") as mock_auth:
            mock_auth.return_value.get_token_from_cache.return_value = None
            with pytest.raises(EntraAuthenticationError):
                MicrosoftGraphClient.from_request(request=object())

    def test_raises_when_token_has_no_access_token(self):
        with patch("projects.graph.AuthHandler") as mock_auth:
            mock_auth.return_value.get_token_from_cache.return_value = {}
            with pytest.raises(EntraAuthenticationError):
                MicrosoftGraphClient.from_request(request=object())


class TestSearchUsers:
    def test_builds_expected_search_request(self):
        captured = {}

        def handler(request):
            captured["request"] = request
            return httpx.Response(200, json={"value": []})

        make_client(handler).search_users("mic", limit=10)

        request = captured["request"]
        assert request.url.path == "/v1.0/users"
        assert request.url.params["$search"] == '"displayName:mic" OR "mail:mic"'
        assert request.url.params["$select"] == "id,displayName,mail"
        assert request.url.params["$top"] == "10"
        assert request.headers["ConsistencyLevel"] == "eventual"

    def test_escapes_double_quotes(self):
        captured = {}

        def handler(request):
            captured["request"] = request
            return httpx.Response(200, json={"value": []})

        make_client(handler).search_users('a"b')

        assert 'a\\"b' in captured["request"].url.params["$search"]

    def test_returns_value_list(self):
        value = [{"id": "id-1", "displayName": "Michael", "mail": "michael@example.gov.uk"}]

        def handler(request):
            return httpx.Response(200, json={"value": value})

        assert make_client(handler).search_users("mic") == value

    @pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
    def test_raises_on_error_response(self, status):
        def handler(request):
            return httpx.Response(status, json={"error": {"code": "Error"}})

        with pytest.raises(EntraRequestError):
            make_client(handler).search_users("mic")

    def test_raises_on_transport_error(self):
        def handler(request):
            raise httpx.TimeoutException("timed out")

        with pytest.raises(EntraRequestError):
            make_client(handler).search_users("mic")


class TestGetUser:
    def test_builds_expected_user_request(self):
        oid = "11111111-1111-1111-1111-111111111111"
        graph_user = {
            "id": oid,
            "displayName": "Real Person",
            "mail": "real.person@justice.gov.uk",
            "givenName": "Real",
            "surname": "Person",
        }
        captured = {}

        def handler(request):
            captured["request"] = request
            return httpx.Response(200, json=graph_user)

        result = make_client(handler).get_user(oid)

        assert result == graph_user
        assert captured["request"].url.path == f"/v1.0/users/{oid}"
        assert captured["request"].url.params["$select"] == "id,displayName,mail,givenName,surname"

    def test_raises_on_error_response(self):
        oid = "22222222-2222-2222-2222-222222222222"

        def handler(request):
            return httpx.Response(404, json={"error": {"code": "NotFound"}})

        with pytest.raises(EntraRequestError):
            make_client(handler).get_user(oid)
