import pytest

from data_platform_app.context_processors import (
    _service_navigation_items_for_request,
    service_navigation,
)


class TestServiceNavigationItems:
    """Tests for the _service_navigation_items_for_request helper."""

    def test_returns_expected_items_for_anonymous_user(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        names = [item["name"] for item in items]
        assert "Roadmap" in names
        assert "Data factories" in names
        assert "App" not in names

    def test_returns_expected_items_for_authenticated_user(self, rf, user):
        request = rf.get("/")
        request.user = user

        items = _service_navigation_items_for_request(request)

        names = [item["name"] for item in items]
        assert "Roadmap" in names
        assert "Data factories" in names
        assert "Home" not in names

    @pytest.mark.parametrize("path", ["/app/", "/app/projects/"])
    def test_returns_app_only_nav_for_app_routes(self, rf, user, path):
        request = rf.get(path)
        request.user = user

        items = _service_navigation_items_for_request(request)

        assert items == [{"name": "Home", "url": "/app/", "active": True}]

    def test_each_item_has_name_and_url(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        for item in items:
            assert "name" in item
            assert "url" in item
            assert "active" in item

    @pytest.mark.parametrize(
        "path",
        [
            "/roadmap/",
            "/roadmap/2025/",
            "/data-factories/",
            "/data-factories/analytics/",
            "/app/",
            "/app/projects/",
            "/other/",
        ],
    )
    def test_active_flag_set_for_matching_path_prefix(self, rf, anonymous_user, path):
        request = rf.get(path)
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        for item in items:
            if path.startswith(item["url"]):
                assert item["active"] is True
                continue
            assert item["active"] is False


class TestServiceNavigationContextProcessor:
    """Tests for the service_navigation context processor."""

    def test_returns_service_navigation_items_key(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        context = service_navigation(request)

        assert "service_navigation_items" in context

    def test_service_navigation_items_is_a_list(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        context = service_navigation(request)

        assert isinstance(context["service_navigation_items"], list)
