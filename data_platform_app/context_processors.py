from django.conf import settings
from django.urls import reverse


def _service_navigation_items_for_request(request):
    """Build shared service navigation items for the current request."""
    app_url = reverse("landing")
    base_items = [
        {"name": "Roadmap", "url": reverse("roadmap")},
        {"name": "Data factories", "url": reverse("data_factories")},
    ]
    app_items = [
        {"name": "Home", "url": app_url},
        {
            "name": "User guide",
            "url": "https://user-guide.data-platform.service.justice.gov.uk/",
        },
    ]

    on_app_route = request.path.startswith(app_url)

    visible_items = app_items if on_app_route else base_items

    matching_item = max(
        (item for item in visible_items if request.path.startswith(item["url"])),
        key=lambda item: len(item["url"]),
        default=None,
    )

    if matching_item is not None:
        matching_item["active"] = True

    return visible_items


def _is_on_app_route(request):
    """Return True if the current request path is within the JDP service (/app/)."""
    return request.path.startswith(reverse("landing"))


def service_navigation(request):
    return {
        "service_navigation_items": _service_navigation_items_for_request(request),
        "on_app_route": _is_on_app_route(request),
    }


def google_analytics(request):
    return {
        "google_analytics_id": settings.GOOGLE_ANALYTICS_ID,
    }


def feature_flags(request):
    """
    Return the feature flags for the current request.

    Example usage in a template:
    {% if FEATURE_FLAGS.EXAMPLE_FEATURE %}
        <a href="{% url 'example_view' %}">Example</a>
    {% endif %}
    """
    return {
        "FEATURE_FLAGS": settings.FEATURE_FLAGS,
    }


def application_metadata(request):
    return {
        "application_version": settings.APPLICATION_VERSION,
        "commit_sha": settings.COMMIT_SHA,
    }
