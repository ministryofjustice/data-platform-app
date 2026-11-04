from uuid import uuid4

from playwright.sync_api import expect


def test_creates_api_key(authenticated_page, e2e_base_url: str, project_uuid: str) -> None:
    page = authenticated_page
    key_name = f"e2e-{uuid4().hex[:12]}"
    key_list_url = f"{e2e_base_url}/app/projects/{project_uuid}/ai-gateway/keys/"

    try:
        page.goto(key_list_url)
        expect(page.get_by_role("heading", name="API keys")).to_be_visible()
        page.get_by_role("link", name="Create API key").click()

        expect(page.get_by_role("heading", name="Create a key")).to_be_visible()
        model_table = page.locator(".govuk-table.moj-multi-select")
        expect(model_table).to_be_visible()
        expect(model_table).not_to_contain_text("No results found.")

        first_model_row = model_table.get_by_role("row").nth(1)
        model_name = first_model_row.locator("td").nth(1).inner_text()
        first_model_row.get_by_role("checkbox").check()
        page.get_by_role("textbox", name="Key name").fill(key_name)
        page.get_by_role("button", name="Continue").click()

        expect(page.get_by_role("heading", name="Review details")).to_be_visible()
        expect(page.locator("body")).to_contain_text(key_name)
        expect(page.locator("body")).to_contain_text(model_name)
        page.get_by_role("button", name="Create key").click()

        expect(page.get_by_role("heading", name="Store your API key")).to_be_visible()
        expect(page.locator("body")).to_contain_text("created an API key for")
        expect(page.locator("#plaintext-key")).not_to_be_empty()
    finally:
        page.goto(key_list_url)
        created_key = page.get_by_role("row").filter(has_text=key_name)
        if created_key.count():
            created_key.get_by_role("link", name="Manage").click()
            page.get_by_role("link", name="Revoke", exact=True).click()
            page.get_by_role("button", name="Revoke", exact=True).click()
            expect(page.locator("body")).to_contain_text(f"You've revoked {key_name}")
