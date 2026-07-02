from django.urls import reverse


def _service_navigation_items_for_request(request):
    """Build shared service navigation items for the current request."""
    app_url = reverse("landing")
    base_items = [
        {"name": "Roadmap", "url": reverse("roadmap")},
        {"name": "Data factories", "url": reverse("data_factories")},
    ]
    app_items = [{"name": "Home", "url": app_url}]

    on_app_route = request.path.startswith(app_url)

    visible_items = app_items if on_app_route else base_items

    for item in visible_items:
        item["active"] = request.path.startswith(item["url"])

    return visible_items


def service_navigation(request):
    return {
        "service_navigation_items": _service_navigation_items_for_request(request),
    }
