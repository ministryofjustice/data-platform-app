def _service_navigation_items_for_request(request):
    """Build shared service navigation items for the current request."""
    # TODO use reverse to build urls when views added for these pages
    items = [
        {"name": "Roadmap", "url": "/roadmap/"},
        {"name": "Data factories", "url": "/data-factories/"},
    ]

    # TODO this is likely to differ in future when users are logged in
    visible_items = items if request.user.is_authenticated else items

    for item in visible_items:
        item["active"] = request.path.startswith(item["url"])

    return visible_items


def service_navigation(request):
    return {
        "service_navigation_items": _service_navigation_items_for_request(request),
    }
