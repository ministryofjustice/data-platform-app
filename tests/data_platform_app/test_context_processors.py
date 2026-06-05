from data_platform_app.context_processors import (
    _service_navigation_items_for_request,
    service_navigation,
)


class TestServiceNavigationItems:
    """Tests for the _service_navigation_items_for_request helper."""

    def test_returns_expected_items(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        names = [item["name"] for item in items]
        assert "Roadmap" in names
        assert "Data factories" in names

    def test_each_item_has_name_and_url(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        for item in items:
            assert "name" in item
            assert "url" in item

    def test_active_flag_set_for_matching_path(self, rf, anonymous_user):
        request = rf.get("/roadmap/")
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        roadmap = next(i for i in items if i["name"] == "Roadmap")
        assert roadmap["active"] is True

    def test_active_flag_not_set_for_non_matching_path(self, rf, anonymous_user):
        request = rf.get("/")
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        for item in items:
            assert item["active"] is False

    def test_active_flag_matches_on_subpath(self, rf, anonymous_user):
        request = rf.get("/roadmap/2025/")
        request.user = anonymous_user

        items = _service_navigation_items_for_request(request)

        roadmap = next(i for i in items if i["name"] == "Roadmap")
        assert roadmap["active"] is True


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
