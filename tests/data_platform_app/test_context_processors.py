import pytest

from data_platform_app.context_processors import (
    _is_on_app_route,
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

    @pytest.mark.parametrize(
        ("path", "expected_active_name"),
        [
            ("/app/", "Home"),
            ("/app/projects/", "Home"),
        ],
    )
    def test_returns_app_only_nav_for_app_routes(self, rf, user, path, expected_active_name):
        request = rf.get(path)
        request.user = user

        items = _service_navigation_items_for_request(request)

        assert [item["name"] for item in items] == ["Home", "User guide"]

        for item in items:
            if item["name"] == expected_active_name:
                assert item["active"] is True
            else:
                assert "active" not in item

    def test_app_nav_includes_user_guide_link(self, rf, user):
        request = rf.get("/app/")
        request.user = user

        items = _service_navigation_items_for_request(request)

        user_guide_items = [item for item in items if item["name"] == "User guide"]
        assert len(user_guide_items) == 1
        assert (
            user_guide_items[0]["url"]
            == "https://user-guide.data-platform.service.justice.gov.uk/"
        )

    def test_each_item_has_name_and_url(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        for item in items:
            assert "name" in item
            assert "url" in item

    @pytest.mark.parametrize(
        ("path", "expected_active_name"),
        [
            ("/roadmap/", "Roadmap"),
            ("/roadmap/2025/", "Roadmap"),
            ("/data-factories/", "Data factories"),
            ("/data-factories/analytics/", "Data factories"),
            ("/app/", "Home"),
            ("/app/projects/", "Home"),
            ("/other/", None),
        ],
    )
    def test_active_flag_set_for_matching_path_prefix(
        self, rf, anonymous_user, path, expected_active_name
    ):
        request = rf.get(path)
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        for item in items:
            if item["name"] == expected_active_name:
                assert item["active"] is True
            else:
                assert "active" not in item


class TestIsOnAppRoute:
    """Tests for the _is_on_app_route helper."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/app/", True),
            ("/app/projects/", True),
            ("/", False),
            ("/roadmap/", False),
            ("/data-factories/", False),
            ("/accessibility-statement/", False),
        ],
    )
    def test_is_on_app_route(self, rf, path, expected):
        request = rf.get(path)

        assert _is_on_app_route(request) is expected


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

    def test_returns_on_app_route_key(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        context = service_navigation(request)

        assert "on_app_route" in context

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/app/", True),
            ("/", False),
        ],
    )
    def test_on_app_route_reflects_path(self, rf, anonymous_user, path, expected):
        request = rf.get(path)
        request.user = anonymous_user

        context = service_navigation(request)

        assert context["on_app_route"] is expected
