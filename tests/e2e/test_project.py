import pytest
from django.conf import settings
from playwright.sync_api import expect

# TODO: Decide whether to keep this local-only project creation test or remove it.
pytestmark = pytest.mark.e2e


def test_creates_project(page, live_server, user, client, business_unit):
    client.force_login(user)

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

    page.goto(live_server.url)

    page.get_by_role("link", name="Get started", exact=True).click()
    page.get_by_role("link", name="Go to projects", exact=True).click()
    page.get_by_role("link", name="Create a project", exact=True).click()

    page.get_by_role("textbox", name="Name").fill("My Test Project")
    page.get_by_role("combobox", name="Business unit").select_option(label=business_unit.name)
    page.get_by_role("textbox", name="Description").fill("This is a test project description.")
    page.get_by_role("button", name="Continue").click()

    page.get_by_label("No").click()
    page.get_by_role("button", name="Continue").click()

    project_details = page.locator(".govuk-summary-card").first
    add_members = page.locator(".govuk-summary-card").last
    expect(project_details).to_be_visible()
    expect(project_details).to_contain_text("My Test Project")
    expect(project_details).to_contain_text("This is a test project description.")
    expect(add_members).to_contain_text("Add members now?")
    expect(add_members).to_contain_text("No")

    page.get_by_role("button", name="Create project").click()

    success_message = page.locator(".moj-alert--success")
    expect(success_message).to_be_visible()
    expect(success_message).to_contain_text("Project created")
