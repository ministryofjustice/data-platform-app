import pytest
from django.conf import settings
from playwright.sync_api import expect

# TODO: Decide whether to remove this legacy model-list check; the key journey is in tests_e2e.
pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def set_playwright_timeout(page):
    page.set_default_timeout(5_000)


def test_creates_key(page, live_server, project, project_owner, client):
    client.force_login(project_owner)

    session_cookie = client.cookies[settings.SESSION_COOKIE_NAME]
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": session_cookie.value,
                "url": live_server.url,
            }
        ]
    )

    page.goto(f"{live_server.url}{project.get_absolute_keys_url()}")

    page.get_by_role("link", name="Create API key").click()
    page.get_by_role("textbox", name="name").fill("My test key")
    model_table = page.locator(".govuk-table.moj-multi-select")
    expect(model_table).to_be_visible()
    expect(model_table).not_to_contain_text("No results found.")
    expect(model_table).to_contain_text("Amazon Bedrock")
